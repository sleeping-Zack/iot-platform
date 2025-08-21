from django.contrib import admin
from django.utils.html import format_html
from .models import Device, EdgeData, Alert, SyncQueue, CloudData, DailySummary, DeviceCredentials
import secrets

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id","device_code","device_name","sensor_type","threshold_hi","last_seen","created_at","has_cred")
    search_fields = ("device_code","device_name","location","sensor_type")
    list_filter = ("sensor_type","location","created_at")
    actions = ["generate_credentials"]

    def has_cred(self, obj):
        return DeviceCredentials.objects.filter(device=obj).exists()
    has_cred.short_description = "Has Credentials"
    has_cred.boolean = True

    def generate_credentials(self, request, queryset):
        created = 0
        for dev in queryset:
            if not DeviceCredentials.objects.filter(device=dev).exists():
                api_key = secrets.token_hex(16)      # 32位hex
                secret  = secrets.token_hex(32)      # 64位hex
                DeviceCredentials.objects.create(device=dev, api_key=api_key, hmac_secret=secret)
                created += 1
        self.message_user(request, f"生成凭证成功：{created} 台设备")
    generate_credentials.short_description = "为选中设备生成 API 凭证"

@admin.register(DeviceCredentials)
class DeviceCredentialsAdmin(admin.ModelAdmin):
    list_display = ("id","device","api_key","hmac_secret","rotated_at")
    search_fields = ("device__device_code","api_key")

@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("id","device","level","message","ts")
    search_fields = ("device__device_code","message")
    list_filter = ("level",)

@admin.register(EdgeData)
class EdgeDataAdmin(admin.ModelAdmin):
    list_display = ("id","device","sensor_value","ts","source_ts","quality")
    search_fields = ("device__device_code",)

@admin.register(SyncQueue)
class SyncQueueAdmin(admin.ModelAdmin):
    list_display = ("id","edge_data","enqueued_at")

@admin.register(CloudData)
class CloudDataAdmin(admin.ModelAdmin):
    list_display = ("id","device_id","sensor_value","ts","synced_at")

@admin.register(DailySummary)
class DailySummaryAdmin(admin.ModelAdmin):
    list_display = ("id","day","device_id","count_records","avg_value","max_value","min_value","alert_count","generated_at")
    list_filter = ("day",)
