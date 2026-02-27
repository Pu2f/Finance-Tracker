from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField
from wtforms.validators import DataRequired, Length, NumberRange


class BudgetForm(FlaskForm):
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    month = StringField("Month", validators=[DataRequired(), Length(min=7, max=7)])
    amount = DecimalField(
        "Budget amount", places=2, validators=[DataRequired(), NumberRange(min=0.01)]
    )
