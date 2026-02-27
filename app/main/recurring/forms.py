from datetime import date

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, DecimalField, IntegerField, SelectField, StringField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class RecurringTransactionForm(FlaskForm):
    type = SelectField(
        "Type",
        choices=[("income", "Income"), ("expense", "Expense")],
        validators=[DataRequired()],
    )
    amount = DecimalField(
        "Amount", places=2, validators=[DataRequired(), NumberRange(min=0.01)]
    )
    frequency = SelectField(
        "Frequency",
        choices=[("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        validators=[DataRequired()],
    )
    interval_count = IntegerField(
        "Every",
        default=1,
        validators=[DataRequired(), NumberRange(min=1, max=365)],
    )
    start_date = DateField("Start date", default=date.today, validators=[DataRequired()])
    end_date = DateField("End date", validators=[Optional()])
    category_id = SelectField("Category", coerce=int, validators=[Optional()])
    note = StringField("Note", validators=[Optional(), Length(max=255)])
    is_active = BooleanField("Active", default=True)

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.end_date.data and self.end_date.data < self.start_date.data:
            self.end_date.errors.append("End date must be on or after start date")
            return False
        return True
