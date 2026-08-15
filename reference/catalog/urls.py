from rest_framework.routers import SimpleRouter

from catalog.views import CategoryViewSet, CollectionViewSet, ProductViewSet, ReviewViewSet

# Every nested prefix embeds its parent's lookup group directly, hand-rolled
# — no router library, same idiom orders/ uses for its one-level nesting.
# This app demonstrates the deeper shapes: two siblings (products,
# collections) under one parent, and a third level (reviews) under one of
# them.
router = SimpleRouter()
router.register("categories", CategoryViewSet, basename="categories")
router.register(r"categories/(?P<category_pk>[^/.]+)/products", ProductViewSet, basename="category-products")
router.register(
    r"categories/(?P<category_pk>[^/.]+)/collections", CollectionViewSet, basename="category-collections"
)
router.register(
    r"categories/(?P<category_pk>[^/.]+)/products/(?P<product_pk>[^/.]+)/reviews",
    ReviewViewSet,
    basename="product-reviews",
)

urlpatterns = router.urls
