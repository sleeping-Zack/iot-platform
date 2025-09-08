# iotcore/views.py
from __future__ import annotations

import datetime
from typing import Optional

from django.db import connection
from django.shortcuts import render, get_object_or_404
from django.utils.dateparse import parse_datetime, parse_date
from rest_framework import viewsets
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt

from .models import Device, EdgeData, Alert, DailySummary, CloudData
from .serializers import DeviceSerializer, AlertSerializer, DailySummarySerializer
from django.utils import timezone
import datetime as _dt
# =========================
# Helpers
# =========================
def _parse_dt(s: Optional[str], *, end: bool = False) -> Optional[datetime.datetime]:
    """
    解析 from/to。支持：
    - 'YYYY-MM-DD'（会补 00:00:00 / 23:59:59）
    - 'YYYY-MM-DDTHH:MM:SS'
    - 以上两种末尾带 Z（按 UTC 解析）
    返回：本地时区 aware datetime
    """
    if not s:
        return None

    s = s.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"  # 让 parse_datetime 识别 UTC

    dt = parse_datetime(s)
    if dt is None:  # 仅日期
        d = parse_date(s)
        if d is None:
            return None
        t = datetime.time(23, 59, 59) if end else datetime.time(0, 0, 0)
        dt = datetime.datetime.combine(d, t)

    # 补齐/转换到本地时区
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    else:
        dt = timezone.localtime(dt, timezone.get_current_timezone())

    return dt


def _to_local_iso(dt: datetime.datetime) -> str:
    """
    把数据库时间转成本地时区，并输出“无时区”的 ISO 字符串（YYYY-MM-DDTHH:MM:SS），
    避免前端再偏移 8 小时。
    """
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    dt = timezone.localtime(dt, timezone.get_current_timezone())
    return dt.strftime("%Y-%m-%dT%H:%M:%S")
from django.conf import settings
from django.utils import timezone

def _to_local_str(dt):
    """
    把 DB 时间安全地转成本地字符串 'YYYY-MM-DD HH:MM:SS'
    - 当 USE_TZ=True：Django 会话通常是 UTC；把 ts 视为 UTC -> 转到本地
    - 当 USE_TZ=False：把 ts 视为“本地 naive”，不做额外偏移
    """
    if dt is None:
        return None
    if timezone.is_aware(dt):
        # 关键：不要 localtime()，直接丢掉 tz，避免再 +8 小时
        dt = dt.replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")



# =========================
# DRF ViewSets（如需）
# =========================
class DeviceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Device.objects.all().order_by("-created_at")
    serializer_class = DeviceSerializer


class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Alert.objects.all().order_by("-ts")
    serializer_class = AlertSerializer


class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DailySummary.objects.all().order_by("-day")
    serializer_class = DailySummarySerializer


# =========================
# Pages
# =========================
def charts_page(request):
    return render(request, "cloud_dashboard.html")


# =========================
# APIs
# =========================
@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def upload_data(request):
    """
    设备/脚本上报：{ "device_code":"T-001", "sensor_value": 26.5 }
    注意：显式写 quality=1，避免历史模型默认 'GOOD' 导致 MySQL 报错。
    """
    try:
        device_code = request.data.get("device_code")
        val = request.data.get("sensor_value")

        if not device_code:
            return Response({"detail": "device_code required"}, status=400)
        try:
            value = float(val)
        except (TypeError, ValueError):
            return Response({"detail": "sensor_value must be number"}, status=400)

        device = Device.objects.filter(device_code=device_code).first()
        if not device:
            return Response({"detail": f"device '{device_code}' not found"}, status=404)

        EdgeData.objects.create(
            device=device,
            sensor_value=value,
            raw_value=value,
            quality=1,   # 关键
        )
        return Response({"ok": True}, status=200)
    except Exception as e:
        import traceback
        print("upload_data error:", e); traceback.print_exc()
        return Response({"detail": f"server error: {e}"}, status=500)


@api_view(["POST"])
def run_sync(request):
    """手动执行：队列 → cloud_data"""
    with connection.cursor() as cur:
        cur.execute("CALL PROC_sync_to_cloud(%s)", [500])
    return Response({"synced": "ok"})


@api_view(["POST"])
def run_daily_report(request):
    """手动生成日报。body 可传 { "day": "YYYY-MM-DD" }，不传则用今天。"""
    day = request.data.get("day")
    with connection.cursor() as cur:
        cur.execute("CALL PROC_generate_report(COALESCE(%s, CURDATE()))", [day])
    return Response({"report": "ok"})


@api_view(["GET"])
def cloud_series(request):
    """
    GET /api/cloud/series?device_code=T-001&limit=500
    可选 from/to（本地或带Z的UTC）。若未提供 from/to，则返回“最新的 limit 条”，并按时间升序输出。
    """
    device_code = request.GET.get("device_code")
    if not device_code:
        return Response({"detail": "device_code required"}, status=400)
    device = get_object_or_404(Device, device_code=device_code)

    from_str = request.GET.get("from")
    to_str   = request.GET.get("to")
    limit    = int(request.GET.get("limit", 500))
    limit    = max(1, min(limit, 5000))

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

    if dt_from or dt_to:
        # 有时间范围：按时间升序取（范围内前 limit 条）
        rows = list(qs.order_by("ts")[:limit])
    else:
        # 无时间范围：默认取“最新的 limit 条”，再反转成升序返回
        rows = list(qs.order_by("-ts")[:limit])[::-1]

    data = [{"ts": _to_local_iso(c.ts), "value": float(c.sensor_value)} for c in rows]
    return Response(data, status=200)


@api_view(["GET"])
def daily_series(request):
    """
    GET /api/report/daily/series?device_code=T-001&days=7
    可选 from/to（同 cloud_series），优先级高于 days。
    """
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


# ========== 前端新增用：实时阈值 & 最近告警 ==========
@api_view(['GET'])
def device_thresholds(request):
    """GET /api/dev/thresholds/?device_code=T-001 -> {threshold_hi, threshold_lo}"""
    code = request.GET.get("device_code")
    dev = get_object_or_404(Device, device_code=code)
    return Response({"threshold_hi": dev.threshold_hi, "threshold_lo": dev.threshold_lo})


@api_view(['GET'])
def recent_alerts(request):
    """
    GET /api/alerts/recent/?device_code=T-001&limit=20
    -> [{id, level, value, ts, message, edge_data_id}, ...]
    """
    code  = request.GET.get("device_code")
    limit = int(request.GET.get("limit", 20))
    dev = get_object_or_404(Device, device_code=code)

    alerts = list(Alert.objects.filter(device_id=dev.id).order_by('-id')[:max(1, min(limit, 200))])
    ed_ids = [a.edge_data_id for a in alerts]
    values = {e.id: e.sensor_value for e in EdgeData.objects.filter(id__in=ed_ids)}

    data = [{
        "id": a.id,
        "level": a.level,                         # HIGH / LOW
        "value": values.get(a.edge_data_id),      # 温度值
        "ts":_to_local_str(a.ts),
        "message": a.message,
        "edge_data_id": a.edge_data_id,
    } for a in alerts]
    return Response(data)