from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional, URL


class LoginForm(FlaskForm):
    password = PasswordField("رمز ورود", validators=[DataRequired(), Length(min=4, max=256)])
    submit = SubmitField("ورود")


class ReviewEditForm(FlaskForm):
    title_fa = StringField("تیتر فارسی", validators=[Optional(), Length(max=600)])
    body_fa = TextAreaField("متن فارسی", validators=[Optional(), Length(max=3500)])
    publish = SubmitField("تأیید و انتشار فوری")
    reject = SubmitField("رد نهایی")


class WebsiteSourceForm(FlaskForm):
    name = StringField("نام منبع", validators=[DataRequired(), Length(max=120)])
    website_url = StringField("آدرس سایت", validators=[DataRequired(), URL(), Length(max=500)])
    feed_url = StringField("RSS / Feed (اختیاری)", validators=[Optional(), URL(), Length(max=500)])
    submit = SubmitField("اضافه کردن سایت")


class XSourceForm(FlaskForm):
    handle = StringField("آی‌دی X / Twitter", validators=[DataRequired(), Length(max=200)])
    name = StringField("نام نمایشی (اختیاری)", validators=[Optional(), Length(max=120)])
    submit = SubmitField("اضافه کردن حساب")
