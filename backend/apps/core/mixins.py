from apps.workspaces.services import active_workspace


class WorkspaceScopedMixin:
    """Restrict a ModelViewSet to the caller's active workspace.

    Assumes the model has a `workspace` FK. Filters list/detail to that
    workspace and stamps it on create, so every member of a workspace shares
    the same data.
    """

    def get_workspace(self):
        return active_workspace(self.request.user)

    def get_queryset(self):
        return super().get_queryset().filter(workspace=self.get_workspace())

    def perform_create(self, serializer):
        serializer.save(workspace=self.get_workspace())
