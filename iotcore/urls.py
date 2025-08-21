from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DeviceViewSet, AlertViewSet, ReportViewSet, upload_data,  run_sync, run_daily_report
from .views import cloud_series, daily_series,charts_page

router = DefaultRouter()
router.register(r'devices', DeviceViewSet)
router.register(r'alerts',  AlertViewSet)
router.register(r'report/daily', ReportViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/data/upload/', upload_data),
    path('api/sync/run/', run_sync),
    path('api/report/run/', run_daily_report),
    path('api/cloud/series', cloud_series),
    path('api/report/daily/series', daily_series),
    path('charts/', charts_page),
]




