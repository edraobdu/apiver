from rest_framework import viewsets

from catalog.models import Category, Collection, Product, Review
from catalog.serializers import CategorySerializer, CollectionSerializer, ProductSerializer, ReviewSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ProductViewSet(viewsets.ModelViewSet):
    """One of two siblings nested under Category — scoped by `category_pk`
    captured from the router prefix."""

    serializer_class = ProductSerializer

    def get_queryset(self):
        return Product.objects.filter(category_id=self.kwargs["category_pk"])

    def perform_create(self, serializer):
        serializer.save(category_id=self.kwargs["category_pk"])


class CollectionViewSet(viewsets.ModelViewSet):
    """The other sibling nested under Category, same parent as Product."""

    serializer_class = CollectionSerializer

    def get_queryset(self):
        return Collection.objects.filter(category_id=self.kwargs["category_pk"])

    def perform_create(self, serializer):
        serializer.save(category_id=self.kwargs["category_pk"])


class ReviewViewSet(viewsets.ModelViewSet):
    """A third level: nested under Product, itself nested under Category —
    scoped by `product_pk` alone, since a product id already implies its
    category."""

    serializer_class = ReviewSerializer

    def get_queryset(self):
        return Review.objects.filter(product_id=self.kwargs["product_pk"])

    def perform_create(self, serializer):
        serializer.save(product_id=self.kwargs["product_pk"])
