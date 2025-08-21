from django.shortcuts import render, get_object_or_404
from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date

from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import (
    Device, EdgeData, Alert, DailySummary, DeviceCredentials, CloudData
)
from .serializers import (
    DeviceSerializer, AlertSerializer, DailySummarySerializer,
    CloudPointSerializer, DailySeriesSerializer,
)

import datetime

class DeviceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Device.objects.all().order_by('-created_at')
    serializer_class = DeviceSerializer

class AlertViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Alert.objects.all().order_by('-ts')
    serializer_class = AlertSerializer

class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DailySummary.objects.all().order_by('-day')
    serializer_class = DailySummarySerializer


@api_view(['POST'])
def upload_data(request):
    """人工测试：单条上报 -> 触发器会告警并入队"""
    device_code = request.data.get("device_code")
    value = float(request.data.get("sensor_value"))
    device = get_object_or_404(Device, device_code=device_code)
    EdgeData.objects.create(device=device, sensor_value=value, raw_value=value)
    return Response({"ok": True})

@api_view(['POST'])
def run_sync(request):
    with connection.cursor() as cur:
        cur.execute("CALL PROC_sync_to_cloud(%s)", [500])
    return Response({"synced": "ok"})

@api_view(['POST'])
def run_daily_report(request):
    day = request.data.get("day")  # 'YYYY-MM-DD'; 若为空则用今天
    with connection.cursor() as cur:
        cur.execute("CALL PROC_generate_report(COALESCE(%s, CURDATE()))", [day])
    return Response({"report": "ok"})


def _parse_dt(s: str, end=False):

    if not s:
        return None
    s = s.strip().replace(' ', 'T')
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    dt = parse_datetime(s)
    if dt is None:
        d = parse_date(s)
        if d is not None:
            t = datetime.time(23, 59, 59) if end else datetime.time(0, 0, 0)
            dt = datetime.datetime.combine(d, t)
    if dt is not None and timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt

@api_view(['GET'])
def cloud_series(request):

    device_code = request.GET.get("device_code")
    if not device_code:
        return Response({"detail": "device_code required"}, status=400)
    device = get_object_or_404(Device, device_code=device_code)

    from_str = request.GET.get("from")
    to_str   = request.GET.get("to")
    limit    = int(request.GET.get("limit", 500))

    dt_from = _parse_dt(from_str, end=False) if from_str else None
    if from_str and dt_from is None:
        return Response({"detail": "invalid from"}, status=400)

    dt_to = _parse_dt(to_str, end=True) if to_str else None
    if to_str and dt_to is None:
        return Response({"detail": "invalid to"}, status=400)

    qs = CloudData.objects.filter(device_id=device.id)
    if dt_from: qs = qs.filter(ts__gte=dt_from)
    if dt_to:   qs = qs.filter(ts__lte=dt_to)
    qs = qs.order_by("ts")[:max(1, min(limit, 5000))]

    data = [{"ts": c.ts, "value": c.sensor_value} for c in qs]
    return Response(CloudPointSerializer(data, many=True).data, status=200)

@api_view(['GET'])
def daily_series(request):

    device_code = request.GET.get("device_code")
    if not device_code:
        return Response({"detail": "device_code required"}, status=400)
    device = get_object_or_404(Device, device_code=device_code)

    to_str   = request.GET.get("to")
    from_str = request.GET.get("from")
    days     = int(request.GET.get("days", 7))

    end_day = None
    start_day = None
    if to_str:
        dt_to = _parse_dt(to_str, end=True)
        if dt_to is None:
            return Response({"detail": "invalid to"}, status=400)
        end_day = dt_to.date()
    if from_str:
        dt_from = _parse_dt(from_str, end=False)
        if dt_from is None:
            return Response({"detail": "invalid from"}, status=400)
        start_day = dt_from.date()

    if not end_day:
        end_day = timezone.now().date()
    if not start_day:
        start_day = end_day - timezone.timedelta(days=max(1, min(days, 90)) - 1)

    qs = DailySummary.objects.filter(
        device_id=device.id,
        day__gte=start_day, day__lte=end_day
    ).order_by("day")

    data = [{
        "day": r.day,
        "avg_value": r.avg_value,
        "max_value": r.max_value,
        "min_value": r.min_value,
        "alert_count": r.alert_count or 0
    } for r in qs]

    return Response(DailySeriesSerializer(data, many=True).data, status=200)


def charts_page(request):
    return render(request, "cloud_dashboard.html")
