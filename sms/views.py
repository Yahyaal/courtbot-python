from datetime import datetime, timedelta
import re

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

import oscn
from twilio.twiml.messaging_response import MessagingResponse

from alerts.models import Alert
from .models import Lookup


@csrf_exempt
def twilio(request):
    resp = MessagingResponse()
    case_num = request.POST['Body']

    # Check case number matches TT-YYYY-NUMBER
    case_re = re.compile('[A-Za-z]{2,2}\-\d{4,4}\-\d{,5}')
    if not case_re.match(case_num):
        resp.message(f'Sorry, case {case_num} does not match the expected format. Please use a'
                    f' full case number like CF-2019-1234')
        return HttpResponse(resp)

    from_phone = request.POST['From']
    # FIXME: no county defaults to Tulsa
    case_county = 'tulsa'
    [case_type, case_year, number] = case_num.split("-")
    case = oscn.request.Case(county=case_county, type=case_type, year=case_year, number=number)
    arraignment_event = find_arraignment_or_return_False(case.events)
    if not arraignment_event:
        resp.message(f'Sorry, I couldn\'t find an arraignment event for case {case_num}')
        return HttpResponse(resp)
    try:
        arraignment_datetime = parse_datetime_from_oscn_event_string(
            arraignment_event.Event
        )
    except e:
        resp.message(f'Sorry, I couldn\'t find an arraignment date for case {case_num}')
        return HttpResponse(resp)

    Lookup.objects.create(
        from_phone=from_phone,
        what=case_num
    )
    resp.message(f'I found {case_num} for ')
    # return HttpResponse(resp)

    week_alert_datetime = arraignment_datetime - timedelta(days=7)
    day_alert_datetime = arraignment_datetime - timedelta(days=1)
    message = f'I will send you a reminder on '
    if week_alert_datetime > datetime.today():
        Alert.objects.create(
            when=week_alert_datetime,
            what=f'Arraignment for case {case_num} in 1 week at {arraignment_datetime}',
            to=from_phone
        )
        message += f'{week_alert_datetime} and on '
    if day_alert_datetime > datetime.today():
        Alert.objects.create(
            when=day_alert_datetime,
            what=f'Arraignment for case {case_num} in 1 day at {arraignment_datetime}',
            to=from_phone
        )
        message += f'{day_alert_datetime}'
    else:
        message = f'Arraignment for case {case_num} has already passed'
    # resp.message(f'I will send you a reminder on {week_alert_datetime} and on {day_alert_datetime}')
    resp.message(message)
    return HttpResponse(resp)


def find_arraignment_or_return_False(events):
    for event in events:
        if "arraignment" in event.Docket.lower():
            return event
    return False


def parse_datetime_from_oscn_event_string(event):
    event = event.replace('ARRAIGNMENT', '').rstrip()
    return datetime.strptime(event, "%A, %B %d, %Y at %I:%M %p")
