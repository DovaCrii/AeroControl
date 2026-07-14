from django.db.models import Q


class SearchMixin:
    """Add text search and the common active/archive filter to list views."""

    search_fields = []

    def get_queryset(self):
        queryset = super().get_queryset()
        query_text = self.request.GET.get("q", "").strip()
        if query_text and self.search_fields:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": query_text})
            queryset = queryset.filter(query)

        active = self.request.GET.get("is_active")
        if active == "active":
            queryset = queryset.filter(is_active=True)
        elif active == "archived":
            queryset = queryset.filter(is_active=False)
        return queryset
