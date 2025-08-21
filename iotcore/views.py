
from __future__ import annotations

import datetime
from typing import Optional

from django.db import connection
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date

from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import (
    Device, EdgeData, Alert, DailySummary, CloudData,  # DeviceCredentials 如需可引入
)
from .serializers import (
    DeviceSerializer, AlertSerializer, DailySummarySerializer,
)

def _parse_dt(s: Optional[str], *, end: bool = False) -> Optional[datetime.datetime]:

    if not s:
        return None

    s = s.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"  # 让 parse_datetime 识别为 UTC

    dt = parse_datetime(s)
    if dt is None:  # 只给了日期
        d = parse_date(s)
        if d is None:
            return None
        t = datetime.time(23, 59, 59) if end else datetime.time(0, 0, 0)
        dt = datetime.datetime.combine(d, t)

    # 补齐时区（按本地时区）
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    else:
        # 有 tz 的话转到本地时区
        dt = timezone.localtime(dt, timezone.get_current_timezone())

    return dt


def _to_local_iso(dt: datetime.datetime) -> str:
    """
    把数据库中的时间转成本地时区，并输出 **无时区** 的 ISO 字符串。
    这样前端 new Date(str) 会按本地解析，避免二次换算。
    """
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    dt = timezone.localtime(dt, timezone.get_current_timezone())
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


class DeviceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Device.objects.all().order_by("-created_at")
    serializer_class = DeviceSerializer


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Alert.objects.all().order_by("-ts")
    serializer_class = AlertSerializer

class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DailySummary.objects.all().order_by("-day")
    serializer_class = DailySummarySerializer

@api_view(["POST"])
def upload_data(request):

    device_code = request.data.get("device_code")
    val = request.data.get("sensor_value")

    if not device_code or val is None:
        return Response({"detail": "device_code & sensor_value required"}, status=400)

    try:
        value = float(val)
    except (TypeError, ValueError):
        return Response({"detail": "sensor_value must be number"}, status=400)

    device = get_object_or_404(Device, device_code=device_code)
    EdgeData.objects.create(device=device, sensor_value=value, raw_value=value)
    return Response({"ok": True})


@api_view(["POST"])
def run_sync(request):
    """手动执行同步存储过程（队列 → cloud_data）"""
    with connection.cursor() as cur:
        cur.execute("CALL PROC_sync_to_cloud(%s)", [500])
    return Response({"synced": "ok"})


@api_view(["POST"])
def run_daily_report(request):
    """手动生成日报。body 可传 { "day": "YYYY-MM-DD" }，不传则用今天。"""
    day = request.data.get("day")
    with connection.cursor() as cur:
        # 让 MySQL 自己 coalesce
        cur.execute("CALL PROC_generate_report(COALESCE(%s, CURDATE()))", [day])
    return Response({"report": "ok"})


#------------------------------
@api_view(["GET"])
def cloud_series(request):
    """
    GET /api/cloud/series?device_code=T-001&from=2025-08-01 00:00:00&to=2025-08-23&limit=500
    - 支持 from/to（本地时间，或末尾 Z 的 UTC）
    - 返回按 ts 升序的 {ts(本地无时区字符串), value}
    """
    device_code = request.GET.get("device_code")
    if not device_code:
        return Response({"detail": "device_code required"}, status=400)
    device = get_object_or_404(Device, device_code=device_code)

    from_str = request.GET.get("from")
    to_str = request.GET.get("to")
    limit = int(request.GET.get("limit", 500))

    dt_from = _parse_dt(from_str, end=False) if from_str else None
    if from_str and dt_from is None:
        return Response({"detail": "invalid from"}, status=400)

    dt_to = _parse_dt(to_str, end=True) if to_str else None
    if to_str and dt_to is None:
        return Response({"detail": "invalid to"}, status=400)

    qs = CloudData.objects.filter(device_id=device.id)
    if dt_from:
        qs = qs.filter(ts__gte=dt_from)
    if dt_to:
        qs = qs.filter(ts__lte=dt_to)
    qs = qs.order_by("ts")[: max(1, min(limit, 5000))]

    data = [{"ts": _to_local_iso(c.ts), "value": float(c.sensor_value)} for c in qs]
    return Response(data, status=200)


@api_view(["GET"])
def daily_series(request):

    device_code = request.GET.get("device_code")
    if not device_code:
        return Response({"detail": "device_code required"}, status=400)
    device = get_object_or_404(Device, device_code=device_code)

    to_str = request.GET.get("to")
    from_str = request.GET.get("from")
    days = int(request.GET.get("days", 7))

    # 计算起止日（本地）
    if to_str:
        dt_to = _parse_dt(to_str, end=True)
        if dt_to is None:
            return Response({"detail": "invalid to"}, status=400)
        end_day = dt_to.date()
    else:
        end_day = timezone.now().date()

    if from_str:
        dt_from = _parse_dt(from_str, end=False)
        if dt_from is None:
            return Response({"detail": "invalid from"}, status=400)
        start_day = dt_from.date()
    else:
        start_day = end_day - timezone.timedelta(days=max(1, min(days, 90)) - 1)

    qs = DailySummary.objects.filter(
        device_id=device.id, day__gte=start_day, day__lte=end_day
    ).order_by("day")

    data = [
        {
            "day": r.day.strftime("%Y-%m-%d"),
            "avg_value": float(r.avg_value) if r.avg_value is not None else None,
            "max_value": float(r.max_value) if r.max_value is not None else None,
            "min_value": float(r.min_value) if r.min_value is not None else None,
            "alert_count": int(r.alert_count or 0),
        }
        for r in qs
    ]
    return Response(data, status=200)

def charts_page(request):
    return render(request, "cloud_dashboard.html")
