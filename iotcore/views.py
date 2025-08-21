from django.shortcuts import render
# Create your views here.
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import connection
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Device, EdgeData, Alert, DailySummary, DeviceCredentials
from .serializers import DeviceSerializer, AlertSerializer, DailySummarySerializer
import hmac, hashlib, json
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.db.models import Q
from django.shortcuts import get_object_or_404
from .models import Device, CloudData, DailySummary
from .serializers import CloudPointSerializer, DailySeriesSerializer



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
    """人工测试：单条上报"""
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


@api_view(['GET'])
def cloud_series(request):
    """
    GET /api/cloud/series?device_code=T-001&from=2025-08-01T00:00:00Z&to=2025-08-21T23:59:59Z&limit=500
    返回 CloudData 时间序列：按 ts 升序，最多 N 点
    """
    device_code = request.GET.get("device_code")
    if not device_code:
        return Response({"detail": "device_code required"}, status=400)
    device = get_object_or_404(Device, device_code=device_code)

    # 过滤条件
    from_str = request.GET.get("from")
    to_str   = request.GET.get("to")
    limit    = int(request.GET.get("limit", 500))

    qs = CloudData.objects.filter(device_id=device.id)
    if from_str:
        dt_from = parse_datetime(from_str)
        if not dt_from: return Response({"detail": "invalid from"}, status=400)
        qs = qs.filter(ts__gte=dt_from)
    if to_str:
        dt_to = parse_datetime(to_str)
        if not dt_to: return Response({"detail": "invalid to"}, status=400)
        qs = qs.filter(ts__lte=dt_to)

    qs = qs.order_by("ts")[:max(1, min(limit, 5000))]

    data = [{"ts": c.ts, "value": c.sensor_value} for c in qs]
    return Response(CloudPointSerializer(data, many=True).data, status=200)

@api_view(['GET'])
def daily_series(request):
    """
    GET /api/report/daily/series?device_code=T-001&days=7
    返回近 N 天的汇总（avg/max/min/alert_count）
    """
    device_code = request.GET.get("device_code")
    days = int(request.GET.get("days", 7))
    if not device_code:
        return Response({"detail": "device_code required"}, status=400)
    device = get_object_or_404(Device, device_code=device_code)

    end_day = timezone.now().date()
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
from django.shortcuts import render

def charts_page(request):
    return render(request, "cloud_dashboard.html")