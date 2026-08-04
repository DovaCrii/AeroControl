from django import template

register = template.Library()


@register.filter
def urgency_bucket(task, today):
    """Wraps KanbanTask.urgency_bucket(today) as a filter -- template methods
    can't take arguments directly."""
    return task.urgency_bucket(today)
