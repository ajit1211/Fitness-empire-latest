"""Rank the existing plans so the upgrade ladder has something to compare.

`tier` defaults to 1 for every row, which would make each plan look like a
sideways move. Numbering them by price, cheapest first, reproduces the ladder
the plans were already priced into (Core, Premier, Executive) without hardcoding
those names.
"""

from django.db import migrations


def number_tiers(apps, schema_editor):
    for model_name in ("Membership", "Membershipmonth"):
        model = apps.get_model("FitnessGYM", model_name)
        for position, plan in enumerate(model.objects.order_by("price", "id"), start=1):
            if plan.tier != position:
                plan.tier = position
                plan.save(update_fields=["tier"])


def reset_tiers(apps, schema_editor):
    for model_name in ("Membership", "Membershipmonth"):
        apps.get_model("FitnessGYM", model_name).objects.update(tier=1)


class Migration(migrations.Migration):
    dependencies = [
        ("FitnessGYM", "0035_alter_membership_options_and_more"),
    ]

    operations = [
        migrations.RunPython(number_tiers, reset_tiers),
    ]
