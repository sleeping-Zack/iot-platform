from django.db import models

class Device(models.Model):
    device_code  = models.CharField(max_length=64, unique=True)
    device_name  = models.CharField(max_length=128)
    location     = models.CharField(max_length=128, blank=True)
    sensor_type  = models.CharField(max_length=64, default="temperature")
    unit         = models.CharField(max_length=16, default="°C", blank=True)
    protocol     = models.CharField(max_length=32, blank=True)  # http/mqtt/modbus
    threshold_hi = models.FloatField(null=True, blank=True)
    threshold_lo = models.FloatField(null=True, blank=True)
    calibration_k= models.FloatField(null=True, blank=True)     # y=kx+b
    calibration_b= models.FloatField(null=True, blank=True)
    fw_version   = models.CharField(max_length=32, blank=True)
    sampling_hz  = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    last_seen    = models.DateTimeField(null=True, blank=True)
    notes        = models.CharField(max_length=255, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta: db_table = "devices"

class EdgeData(models.Model):
    device       = models.ForeignKey(Device, on_delete=models.CASCADE)
    sensor_value = models.FloatField()                 # 校准后（可直接等于 raw）
    raw_value    = models.FloatField(null=True, blank=True)
    ts           = models.DateTimeField(auto_now_add=True)  # 服务器接收时刻
    source_ts    = models.DateTimeField(null=True, blank=True)  # 设备自带时间
    quality      = models.IntegerField(default=1, choices=[(1,"GOOD"), (0,"BAD")])
    meta         = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "edge_data"
        indexes = [models.Index(fields=["device","ts"])]

class Alert(models.Model):
    device    = models.ForeignKey(Device, on_delete=models.CASCADE)
    edge_data = models.ForeignKey(EdgeData, on_delete=models.CASCADE)
    level     = models.CharField(max_length=16)  # HIGH/LOW
    message   = models.CharField(max_length=512, blank=True)
    ts        = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "alerts"
        indexes = [models.Index(fields=["device","ts"])]

class SyncQueue(models.Model):
    edge_data   = models.OneToOneField(EdgeData, on_delete=models.CASCADE)
    enqueued_at = models.DateTimeField(auto_now_add=True)

    class Meta: db_table = "sync_queue"

class CloudData(models.Model):
    device_id   = models.IntegerField()
    sensor_value= models.FloatField()
    ts          = models.DateTimeField()
    synced_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cloud_data"
        indexes = [models.Index(fields=["device_id","ts"])]

class DailySummary(models.Model):
    day           = models.DateField()
    device_id     = models.IntegerField()
    count_records = models.IntegerField()
    avg_value     = models.FloatField(null=True)
    max_value     = models.FloatField(null=True)
    min_value     = models.FloatField(null=True)
    alert_count   = models.IntegerField(default=0)
    generated_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "daily_summary"
        unique_together = ("day","device_id")

class DeviceCredentials(models.Model):
    device     = models.ForeignKey(Device, on_delete=models.CASCADE)
    api_key    = models.CharField(max_length=64, unique=True)
    hmac_secret= models.CharField(max_length=64)
    rotated_at = models.DateTimeField(auto_now_add=True)

    class Meta: db_table = "device_credentials"
