from flask_wtf import FlaskForm
from wtforms import SelectField, StringField
from wtforms.validators import DataRequired, Length


class CategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=80)])
    type = SelectField("Type", choices=[("income", "Income"), ("expense", "Expense")], validators=[DataRequired()])