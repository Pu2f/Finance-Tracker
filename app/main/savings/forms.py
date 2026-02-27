from datetime import date

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, DecimalField, StringField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class SavingsGoalForm(FlaskForm):
    name = StringField("Goal name", validators=[DataRequired(), Length(max=120)])
    target_amount = DecimalField(
        "Target amount", places=2, validators=[DataRequired(), NumberRange(min=0.01)]
    )
    current_amount = DecimalField(
        "Current saved", places=2, default=0, validators=[DataRequired(), NumberRange(min=0)]
    )
    monthly_plan_amount = DecimalField(
        "Monthly plan",
        places=2,
        default=0,
        validators=[DataRequired(), NumberRange(min=0)],
    )
    start_date = DateField("Start date", default=date.today, validators=[DataRequired()])
    target_date = DateField("Target date", validators=[Optional()])
    is_active = BooleanField("Active", default=True)

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators=extra_validators):
            return False
        if self.target_date.data and self.target_date.data < self.start_date.data:
            self.target_date.errors.append("Target date must be on or after start date")
            return False
        return True


class SavingsContributionForm(FlaskForm):
    amount = DecimalField(
        "Add amount", places=2, validators=[DataRequired(), NumberRange(min=0.01)]
    )
