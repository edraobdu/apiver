from rest_framework_nested import routers

from catalog.views import CategoryViewSet, ProductViewSet

# Nested-router spike, third-party-library variant (contrast with orders/'s
# hand-rolled regex prefix): NestedSimpleRouter derives
# "categories/(?P<category_pk>[^/.]+)/products" for us from the parent
# router + lookup name.
router = routers.SimpleRouter()
router.register("categories", CategoryViewSet, basename="categories")

products_router = routers.NestedSimpleRouter(router, "categories", lookup="category")
products_router.register("products", ProductViewSet, basename="category-products")

urlpatterns = router.urls + products_router.urls
