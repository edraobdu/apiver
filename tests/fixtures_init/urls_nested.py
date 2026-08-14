from rest_framework.routers import SimpleRouter

from . import views

# A pre-existing project's nested resource, expressed the way DRF users
# actually write it with no extra library: the parent's lookup group
# embedded directly in the child's own router prefix. Exercises init's
# adoption walk against that shape (tests.fixtures_init.settings_nested).
router = SimpleRouter()
router.register("parents", views.WidgetViewSet, basename="parents")
router.register(r"parents/(?P<parent_pk>[^/.]+)/children", views.ChildViewSet, basename="parent-children")

urlpatterns = router.urls
