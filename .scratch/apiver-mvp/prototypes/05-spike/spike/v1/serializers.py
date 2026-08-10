from rest_framework import serializers

from spike.models import Order, Payment, UserProfile


class UserV1Serializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["id", "username", "email"]


class PaymentV1Serializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "amount", "currency"]


class OrderV1Serializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ["id", "reference"]
