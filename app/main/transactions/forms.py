from datetime import date

from flask_wtf import FlaskForm
from wtforms import DateField, DecimalField, SelectField, StringField
from wtforms.validators import DataRequired, NumberRange, Optional, Length


class TransactionForm(FlaskForm):
    type = SelectField("Type", choices=[("income", "Income"), ("expense", "Expense")], validators=[DataRequired()])
    amount = DecimalField("Amount", places=2, validators=[DataRequired(), NumberRange(min=0.01)])
    tx_date = DateField("Date", default=date.today, validators=[DataRequired()])
    category_id = SelectField("Category", coerce=int, validators=[Optional()])
    category_name = StringField("Or new category", validators=[Optional(), Length(max=80)])
    tags = StringField("Tags", validators=[Optional(), Length(max=255)])
    note = StringField("Note", validators=[Optional(), Length(max=255)])
