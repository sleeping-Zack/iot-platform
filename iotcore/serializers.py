from rest_framework import serializers
from .models import Device, Alert, DailySummary

class DeviceSerializer(serializers.ModelSerializer):
    class Meta: model = Device; fields = "__all__"

class AlertSerializer(serializers.ModelSerializer):
    class Meta: model = Alert; fields = "__all__"

class DailySummarySerializer(serializers.ModelSerializer):
    class Meta: model = DailySummary; fields = "__all__"
from rest_framework import serializers

class CloudPointSerializer(serializers.Serializer):
    ts = serializers.CharField()
    value = serializers.FloatField()

class DailySeriesSerializer(serializers.Serializer):
    day = serializers.DateField()
    avg_value = serializers.FloatField(allow_null=True)
    max_value = serializers.FloatField(allow_null=True)
    min_value = serializers.FloatField(allow_null=True)
    alert_count = serializers.IntegerField()
