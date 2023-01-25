"""
Main module serving the pages for the bunq2IFTTT appengine app
"""

import json
import os

import arrow

from flask import Flask, request, render_template

import auth
import bunq
import card
import event
import payment
import paymentrequest
import storage
import targetbalance
import util
import auth
import requests
from config import settings

# pylint: disable=invalid-name
app = Flask(__name__)
# pylint: enable=invalid-name


###############################################################################
# Webpages
###############################################################################

@app.route("/")
def home_get():
    """ Endpoint for the homepage """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("start.html")

    config = bunq.retrieve_config()
    bunqkeymode = config.get("mode")

    iftttkeyset = (util.get_ifttt_service_key("") is not None)
    accounts = util.get_bunq_accounts_with_permissions(config)
    enableexternal = util.get_external_payment_enabled()
    bunq_oauth = storage.get_value("bunq2IFTTT", "bunq_oauth")
    if bunq_oauth is not None and bunqkeymode != "APIkey":
        expire = arrow.get(bunq_oauth["timestamp"] + 90*24*3600)
        oauth_expiry = "{} ({})".format(expire.humanize(), expire.isoformat())
    else:
        oauth_expiry = None
    # Google AppEngine does not provide fixed ip addresses
    defaultallips = (os.getenv("GAE_INSTANCE") is not None)

    return render_template("main.html",\
        iftttkeyset=iftttkeyset, bunqkeymode=bunqkeymode, accounts=accounts,\
        enableexternal=enableexternal, defaultallips=defaultallips,\
        oauth_expiry=oauth_expiry)


@app.route("/login", methods=["POST"])
def user_login():
    """ Endpoint for login password submission """
    return auth.user_login()


@app.route("/set_ifttt_service_key", methods=["POST"])
def set_ifttt_service_key():
    """ Endpoint for IFTTT service key submission """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    return auth.set_ifttt_service_key()

@app.route("/set_bunq_oauth_api_key", methods=["POST"])
def set_bunq_oauth_api_key():
    """ Endpoint for bunq OAuth keys / API key submission """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    return auth.set_bunq_oauth_api_key()

@app.route("/bunq_oauth_reauthorize", methods=["GET"])
def bunq_oauth_reauthorize():
    """ Endpoint to reauthorize OAuth with bunq """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    return auth.bunq_oauth_reauthorize()

@app.route("/auth", methods=["GET"])
def set_bunq_oauth_response():
    """ Endpoint for the bunq OAuth response """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    return auth.set_bunq_oauth_response()

@app.route("/update_accounts", methods=["GET"])
def update_accounts():
    """ Endpoint to update the list of bunq accounts """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    util.update_bunq_accounts()
    return render_template("message.html", msgtype="success", msg=\
        'Account update completed<br><br>'\
        '<a href="/">Click here to return home</a>')

@app.route("/account_change_permission", methods=["GET"])
def account_change_permission():
    """ Enable/disable a permissions for an account """
    cookie = request.cookies.get('session')
    if cookie is None or cookie != util.get_session_cookie():
        return render_template("message.html", msgtype="danger", msg=\
            "Invalid request: session cookie not set or not valid")
    if util.account_change_permission(request.args["iban"],
                                      request.args["permission"],
                                      request.args["value"]):
        return render_template("message.html", msgtype="success", msg=\
            'Status changed<br><br>'\
            '<a href="/">Click here to return home</a>')
    return render_template("message.html", msgtype="danger", msg=\
        'Something went wrong, please check the logs!<br><br>'\
        '<a href="/">Click here to return home</a>')


###############################################################################
# Helper methods
###############################################################################

def check_ifttt_service_key():
    """ Helper method to check the IFTTT-Service-Key header """
    if "IFTTT-Service-Key" not in request.headers:
        return json.dumps({"errors": [{"message": "Missing IFTTT key"}]})
    if request.headers["IFTTT-Service-Key"] \
    != util.get_ifttt_service_key(request.headers["IFTTT-Service-Key"]):
        return json.dumps({"errors": [{"message": "Invalid IFTTT key"}]})
    return None

def check_access_token():
    """ Helper method to check the Access Token header """
    if "Authorization" not in request.headers:
        return json.dumps({"errors": [{"message": "Missing access token header"}]})
    result = auth.VerifyToken(request.headers.get('Authorization').split()[1]).verify()
    if result.get("status"):
        return json.dumps({"errors": [{"message": "Error in verifying access token"}]})
    return None

###############################################################################
# Cron endpoints
###############################################################################

@app.route("/cron/clean_seen")
def clean_seen():
    """ Clean the seen cache periodically """
    if os.getenv("GAE_INSTANCE") is not None:
        if "X-Appengine-Cron" not in request.headers\
        or request.headers["X-Appengine-Cron"] != "true":
            print("Invalid cron call")
            return "Invalid cron call"
    else:
        host = request.host
        if host.find(":") > -1:
            host = host[:host.find(":")]
        if host not in ["127.0.0.1", "localhost"]:
            return "Invalid cron call"

    storage.clean_seen("seen_mutation")
    storage.clean_seen("seen_request")
    return ""


###############################################################################
# Status / testing endpoints
###############################################################################

@app.route("/ifttt/v1/status")
def ifttt_status():
    """ Status endpoint for IFTTT platform endpoint tests """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    return ""

@app.route("/ifttt/v1/user/info")
def ifttt_user_info():
    """ User info endpoint for IFTTT platform endpoint tests """
    errmsg = check_access_token()
    if errmsg:
        return errmsg, 401
    headers = { 'content-type': "application/json", 'Authorization': f"Bearer {request.headers.get('Authorization').split()[1]}" }
    res = requests.get(settings.auth0_userinfo, headers=headers)

    data = res.json()

    return json.dumps({
        "data": {
            "id": data["sub"],
            "name": data["name"],
            "url": "http//example.com/users/shaunaa126"
        }
    })

@app.route("/ifttt/v1/test/setup", methods=["POST"])
def ifttt_test_setup():
    """ Testdata endpoint for IFTTT platform endpoint tests """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    test_account = "NL42BUNQ0123456789"

    return json.dumps({
        "data": {
            "accessToken": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Ik5qcHNaMVZkT1pwRWpGdmNNV2FqcCJ9.eyJpc3MiOiJodHRwczovL2Rldi04c21oNHBhZndyMThpeXdoLnVzLmF1dGgwLmNvbS8iLCJzdWIiOiJhdXRoMHw2MzliN2JhMjljNDNjZDZmNzRlN2NhOWUiLCJhdWQiOlsibnVpc3RpY3Mtc2VydmljZS1hcGkiLCJodHRwczovL2Rldi04c21oNHBhZndyMThpeXdoLnVzLmF1dGgwLmNvbS91c2VyaW5mbyJdLCJpYXQiOjE2NzQ2MDE5MDUsImV4cCI6MTY3NDY4ODMwNSwiYXpwIjoiV3U4SThjZU1EbklGYlFPYzFtVGl0elNtVm0zOU41blciLCJzY29wZSI6Im9wZW5pZCBwcm9maWxlIGVtYWlsIGlmdHR0IG9mZmxpbmVfYWNjZXNzIn0.CJgmHsb2FThi5FyDMytAFPsJq0Tci8LoR7F7MZMIvazPAauqop0q6vnAWM-No2HMO-d0iz-ywMvgutHMI0uR89nifKdvoNziUvaBLBnee0H7HCMws-anhAgxtlHsVfz0x1KR4LhFSEHNw3dCbCVoq0Gddyd1jzSR_2Umo31nNA-iejE4KIbrCh4AojYXzNsF5Rtis4yK7TL14TJqvetoNghH50coNdOXHMajsxVULPUVWDN9xDwVf9d1bYA3qY-DGncMsX0qzTyLdob9TEd5AhxzIzCjarAms_mMreJmbEqb9UwgZf0-2NmB7zCjIrrFQ_uQARWdVDehsICyubbFDA",
            "samples": {
                "triggers": {
                    "bunq_mutation": {
                        "account": test_account,
                        "type": "ANY",
                        "type_2": "ANY",
                        "type_3": "ANY",
                        "type_4": "ANY",
                        "amount_comparator": "above",
                        "amount_value": "0",
                        "amount_comparator_2": "below",
                        "amount_value_2": "99999",
                        "balance_comparator": "above",
                        "balance_value": "0",
                        "balance_comparator_2": "below",
                        "balance_value_2": "99999",
                        "counterparty_name_comparator": "not_equal",
                        "counterparty_name_value": "Foo bar",
                        "counterparty_name_comparator_2": "not_equal",
                        "counterparty_name_value_2": "Foo bar",
                        "counterparty_account_comparator": "not_equal",
                        "counterparty_account_value": "Foo bar",
                        "counterparty_account_comparator_2": "not_equal",
                        "counterparty_account_value_2": "Foo bar",
                        "description_comparator": "not_equal",
                        "description_value": "Foo bar",
                        "description_comparator_2": "not_equal",
                        "description_value_2": "Foo bar",
                    },
                    "bunq_balance": {
                        "account": test_account,
                        "balance_comparator": "above",
                        "balance_value": "0",
                        "balance_comparator_2": "below",
                        "balance_value_2": "99999",
                    },
                    "bunq_request": {
                        "account": test_account,
                        "amount_comparator": "above",
                        "amount_value": "0",
                        "amount_comparator_2": "below",
                        "amount_value_2": "99999",
                        "counterparty_name_comparator": "not_equal",
                        "counterparty_name_value": "Foo bar",
                        "counterparty_name_comparator_2": "not_equal",
                        "counterparty_name_value_2": "Foo bar",
                        "counterparty_account_comparator": "not_equal",
                        "counterparty_account_value": "Foo bar",
                        "counterparty_account_comparator_2": "not_equal",
                        "counterparty_account_value_2": "Foo bar",
                        "description_comparator": "not_equal",
                        "description_value": "Foo bar",
                        "description_comparator_2": "not_equal",
                        "description_value_2": "Foo bar",
                    },
                    "bunq_oauth_expires": {
                        "hours": "9876543210",
                    },
                    "nuistics_newimage": {
                        "account": test_account,
                        "description_comparator": "equal",
                        "description_value": "dog",
                    }
                },
                "actions": {
                    "bunq_internal_payment": {
                        "amount": "1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "description": "x",
                    },
                    "bunq_external_payment": {
                        "amount": "1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "target_name": "John Doe",
                        "description": "x",
                    },
                    "bunq_draft_payment": {
                        "amount": "1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "target_name": "John Doe",
                        "description": "x",
                    },
                    "bunq_change_card_account": {
                        "card": "x",
                        "account": test_account,
                        "pin_ordinal": "PRIMARY"
                    },
                    "bunq_request_inquiry": {
                        "amount": "1.23",
                        "account": test_account,
                        "phone_email_iban": test_account,
                        "description": "x",
                    },
                    "bunq_target_balance_internal": {
                        "account": test_account,
                        "amount": "123.45",
                        "other_account": test_account,
                        "direction": "top up or skim",
                        "payment_type": "DIRECT",
                        "description": "x",
                    },
                    "bunq_target_balance_external": {
                        "account": test_account,
                        "amount": "123.45",
                        "direction": "top up or skim",
                        "payment_account": test_account,
                        "payment_name": "John Doe",
                        "payment_description": "x",
                        "request_phone_email_iban": test_account,
                        "request_description": "x",
                    },
                },
                "actionRecordSkipping": {
                    "bunq_internal_payment": {
                        "amount": "-1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "description": "x",
                    },
                    "bunq_external_payment": {
                        "amount": "-1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "target_name": "John Doe",
                        "description": "x",
                    },
                    "bunq_draft_payment": {
                        "amount": "-1.23",
                        "source_account": test_account,
                        "target_account": test_account,
                        "target_name": "John Doe",
                        "description": "x",
                    },
                    "bunq_target_balance_internal": {
                        "account": test_account,
                        "amount": "-123.45",
                        "other_account": test_account,
                        "direction": "top up or skim",
                        "payment_type": "DIRECT",
                        "description": "x",
                    },
                    "bunq_target_balance_external": {
                        "account": test_account,
                        "amount": "-123.45",
                        "direction": "top up or skim",
                        "payment_account": test_account,
                        "payment_name": "John Doe",
                        "payment_description": "x",
                        "request_phone_email_iban": test_account,
                        "request_description": "x",
                    },
                }
            }
        }
    })


###############################################################################
# Option value endpoints
###############################################################################

@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "amount_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "amount_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "balance_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "balance_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_balance/fields/"\
           "balance_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_balance/fields/"\
           "balance_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "amount_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "amount_comparator_2/options", methods=["POST"])
def ifttt_comparator_numeric_options():
    """ Option values for numeric comparators """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    data = {"data": [
        {"value": "ignore", "label": "ignore"},
        {"value": "equal", "label": "equal to"},
        {"value": "not_equal", "label": "not equal to"},
        {"value": "above", "label": "above"},
        {"value": "above_equal", "label": "above or equal to"},
        {"value": "below", "label": "below"},
        {"value": "below_equal", "label": "below or equal to"},
        {"value": "in", "label": "in [json array]"},
        {"value": "not_in", "label": "not in [json array]"},
    ]}
    return json.dumps(data)

@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "counterparty_name_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "counterparty_name_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "counterparty_account_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "counterparty_account_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "description_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "description_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "counterparty_name_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "counterparty_name_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "counterparty_account_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "counterparty_account_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "description_comparator/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "description_comparator_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/nuistics_newimage/fields/"\
           "description_comparator/options", methods=["POST"])
def ifttt_comparator_alpha_options():
    """ Option values for alphanumeric comparators """
    # errmsg = check_ifttt_service_key()
    errmsg = check_access_token()
    if errmsg:
        return errmsg, 401

    data = {"data": [
        {"value": "ignore", "label": "ignore"},
        {"value": "equal", "label": "is equal to"},
        {"value": "not_equal", "label": "is not equal to"},
        {"value": "cont", "label": "contains"},
        {"value": "not_cont", "label": "does not contain"},
        {"value": "equal_nc", "label": "is equal to (ignore case)"},
        {"value": "not_equal_nc", "label": "is not equal to (ignore case)"},
        {"value": "cont_nc", "label": "contains (ignore case)"},
        {"value": "not_cont_nc", "label": "does not contain (ignore case)"},
        {"value": "in", "label": "in [json array]"},
        {"value": "not_in", "label": "not in [json array]"},
        {"value": "in_nc", "label": "in [json array] (ignore case)"},
        {"value": "not_in_nc", "label": "not in [json array] (ignore case)"},
    ]}
    return json.dumps(data)

@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "type/options", methods=["POST"])
def ifttt_type_options_1():
    """ Option values for the first type field """
    return ifttt_type_options(True)

@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "type_2/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "type_3/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "type_4/options", methods=["POST"])
def ifttt_type_options_2():
    """ Option values for the subsequent type fields """
    return ifttt_type_options(False)

def ifttt_type_options(first):
    """ Option values for the type fields """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    if first:
        data = {"data": [{"value": "ANY", "label": "ANY"}]}
    else:
        data = {"data": [{"value": "---", "label": "---"}]}

    data["data"].extend([
        {"value": "BUNQ", "label": "BUNQ (all subtypes)"},
        {"value": "BUNQ_BILLING", "label": "BUNQ_BILLING"},
        {"value": "BUNQ_INTEREST", "label": "BUNQ_INTEREST"},
        {"value": "BUNQ_REWARD", "label": "BUNQ_REWARD"},
        {"value": "CARD", "label": "CARD (all subtypes)"},
        {"value": "CARD_PAYMENT", "label": "CARD_PAYMENT"},
        {"value": "CARD_REVERSAL", "label": "CARD_REVERSAL"},
        {"value": "CARD_WITHDRAWAL", "label": "CARD_WITHDRAWAL"},
        {"value": "ONLINE", "label": "ONLINE (all subtypes)"},
        {"value": "ONLINE_IDEAL", "label": "ONLINE_IDEAL"},
        {"value": "ONLINE_SOFORT", "label": "ONLINE_SOFORT"},
        {"value": "TRANSFER", "label": "TRANSFER (all subtypes)"},
        {"value": "TRANSFER_REGULAR", "label": "TRANSFER_REGULAR"},
        {"value": "TRANSFER_REQUEST", "label": "TRANSFER_REQUEST"},
        {"value": "TRANSFER_SAVINGS", "label": "TRANSFER_SAVINGS"},
        {"value": "TRANSFER_SCHEDULED", "label": "TRANSFER_SCHEDULED"},
    ])
    return json.dumps(data)


@app.route("/ifttt/v1/triggers/bunq_mutation/fields/"\
           "account/options", methods=["POST"])
@app.route("/ifttt/v1/triggers/bunq_balance/fields/"\
           "account/options", methods=["POST"])
def ifttt_account_options_mutation():
    """ Option values for mutation/balance trigger account selection"""
    return ifttt_account_options(True, "Mutation")

@app.route("/ifttt/v1/triggers/bunq_request/fields/"\
           "account/options", methods=["POST"])
def ifttt_account_options_request():
    """ Option values for request trigger account selection"""
    return ifttt_account_options(True, "Request")

@app.route("/ifttt/v1/triggers/nuistics_newimage/fields/"\
           "account/options", methods=["POST"])
def ifttt_account_options_newimage():
    """ Option values for newimage account selection"""
    # errmsg = check_ifttt_service_key()
    errmsg = check_access_token()
    if errmsg:
        return errmsg, 401
    data = {"data": [
        {"value": "NL42BUNQ0123456789", "label": "NL42BUNQ0123456789"},
        {"value": "NL42BUNQ9876543210", "label": "NL42BUNQ9876543210"},
    ]}
    return json.dumps(data)
    #return ifttt_account_options(False, None)

@app.route("/ifttt/v1/actions/bunq_internal_payment/fields/"\
           "source_account/options", methods=["POST"])
def ifttt_account_options_internal_source():
    """ Option values for internal payment source account selection"""
    return ifttt_account_options(False, "Internal")

@app.route("/ifttt/v1/actions/bunq_internal_payment/fields/"\
           "target_account/options", methods=["POST"])
def ifttt_account_options_internal_target():
    """ Option values for internal payment target account selection"""
    return ifttt_account_options(False, None)

@app.route("/ifttt/v1/actions/bunq_draft_payment/fields/"\
           "source_account/options", methods=["POST"])
def ifttt_account_options_draft():
    """ Option values for draft payment source account selection"""
    return ifttt_account_options(False, "Draft")

@app.route("/ifttt/v1/actions/bunq_external_payment/fields/"\
           "source_account/options", methods=["POST"])
def ifttt_account_options_external():
    """ Option values for draft payment source account selection"""
    return ifttt_account_options(False, "External")

@app.route("/ifttt/v1/actions/bunq_change_card_account/fields/"\
           "account/options", methods=["POST"])
def ifttt_account_options_change_card():
    """ Option values for change card account selection"""
    return ifttt_account_options(False, "Card")

@app.route("/ifttt/v1/actions/bunq_request_inquiry/fields/"\
           "account/options", methods=["POST"])
def ifttt_account_options_request_inquiry():
    """ Option values for request inquiry source account selection"""
    return ifttt_account_options(False, "PaymentRequest")

@app.route("/ifttt/v1/actions/bunq_target_balance_internal/fields/"\
           "account/options", methods=["POST"])
def ifttt_account_options_target_balance_internal():
    """ Option values for internal target balance account selection"""
    return ifttt_account_options(False, None)

@app.route("/ifttt/v1/actions/bunq_target_balance_internal/fields/"\
           "other_account/options", methods=["POST"])
def ifttt_account_options_target_balance_internal_other():
    """ Option values for internal target balance other account selection"""
    return ifttt_account_options(False, None)

@app.route("/ifttt/v1/actions/bunq_target_balance_external/fields/"\
           "account/options", methods=["POST"])
def ifttt_account_options_target_balance_external():
    """ Option values for external target balance account selection"""
    return ifttt_account_options(False, None)

def ifttt_account_options(include_any, enable_key):
    """ Option values for account selection """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401

    config = bunq.retrieve_config()
    accounts = util.get_bunq_accounts_with_permissions(config)

    if include_any:
        data = {"data": [{"label": "ANY", "value": "ANY"}]}
    else:
        data = {"data": []}

    for acc in accounts:
        if enable_key is None or (enable_key in acc["perms"] and
                                  acc["perms"][enable_key]):
            ibanstr = acc["iban"]
            iban_formatted = ""
            while len(ibanstr) > 4:
                iban_formatted += ibanstr[:4] + " "
                ibanstr = ibanstr[4:]
            iban_formatted += ibanstr
            data["data"].append({
                "label": "{} ({})".format(acc["description"],
                                          iban_formatted),
                "value": acc["iban"]
            })
    return json.dumps(data)


@app.route("/ifttt/v1/actions/bunq_change_card_account/fields/"\
           "card/options", methods=["POST"])
def ifttt_card_options():
    """ Option values for card selection"""
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return json.dumps({"data": card.get_bunq_cards()})


@app.route("/ifttt/v1/actions/bunq_change_card_account/fields/"\
           "pin_ordinal/options", methods=["POST"])
def ifttt_card_pin_options():
    """ Option values for the pin ordinal selection"""
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return json.dumps({"data": [{
        "label": "PRIMARY",
        "value": "PRIMARY"
    }, {
        "label": "SECONDARY",
        "value": "SECONDARY"
    }]})


@app.route("/ifttt/v1/actions/bunq_target_balance_internal/fields/"\
           "direction/options", methods=["POST"])
@app.route("/ifttt/v1/actions/bunq_target_balance_external/fields/"\
           "direction/options", methods=["POST"])
def ifttt_target_balance_direction_options():
    """ Option values for the direction field in the target balance actions"""
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return json.dumps({"data": [{
        "value": "top up or skim",
        "label": "Both - add/top up or remove/skim money depending on balance"
    }, {
        "value": "skim",
        "label": "Skim only - only remove, don't add money"
    }, {
        "value": "top up",
        "label": "Top up only - only add, don't remove money"
    }]})


@app.route("/ifttt/v1/actions/bunq_target_balance_internal/fields/"\
           "payment_type/options", methods=["POST"])
def ifttt_target_balance_payment_type_options():
    """ Option values for the payment type in the target balance action"""
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return json.dumps({"data": [{
        "value": "DIRECT",
        "label": "Direct payment - no approval needed"
    }, {
        "value": "DRAFT",
        "label": "Draft payment - requiring approval in the bunq app"
    }]})


###############################################################################
# Bunq callback endpoints
###############################################################################

@app.route("/bunq_callback_mutation", methods=["POST"])
@app.route("/bunq2ifttt_mutation", methods=["POST"])
def bunq2ifttt_mutation():
    """ Callback for bunq MUTATION events """
    return "", event.bunq_callback_mutation()

@app.route("/bunq_callback_request", methods=["POST"])
@app.route("/bunq2ifttt_request", methods=["POST"])
def bunq2ifttt_request():
    """ Callback for bunq REQUEST events """
    return "", event.bunq_callback_request()

@app.route("/nuistics_request", methods=["POST"])
def nuistics_request():
    """ Callback for nuistics REQUEST events """
    return "", event.nuistics_callback_request()

###############################################################################
# Event trigger endpoints
###############################################################################

@app.route("/ifttt/v1/triggers/bunq_mutation", methods=["POST"])
def trigger_mutation():
    """ Retrieve bunq_mutation trigger items """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_mutation()

@app.route("/ifttt/v1/triggers/bunq_mutation/trigger_identity/<triggerid>",
           methods=["DELETE"])
def trigger_mutation_delete(triggerid):
    """ Delete a trigger_identity for the bunq_mutation trigger """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_mutation_delete(triggerid)

@app.route("/ifttt/v1/triggers/bunq_balance", methods=["POST"])
def trigger_balance():
    """ Retrieve bunq_balance trigger items """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_balance()

@app.route("/ifttt/v1/triggers/bunq_balance/trigger_identity/<triggerid>",
           methods=["DELETE"])
def trigger_balance_delete(triggerid):
    """ Delete a trigger_identity for the bunq_balance trigger """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_balance_delete(triggerid)

@app.route("/ifttt/v1/triggers/bunq_request", methods=["POST"])
def trigger_request():
    """ Retrieve bunq_balance trigger items """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_request()

@app.route("/ifttt/v1/triggers/bunq_request/trigger_identity/<triggerid>",
           methods=["DELETE"])
def trigger_request_delete(triggerid):
    """ Delete a trigger_identity for the bunq_request trigger """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_request_delete(triggerid)

@app.route("/ifttt/v1/triggers/bunq_oauth_expires", methods=["POST"])
def trigger_oauth_expires():
    """ Retrieve bunq_oauth_expires trigger items """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_oauth_expires()

@app.route("/ifttt/v1/triggers/bunq_oauth_expires/trigger_identity/"\
           "<triggerid>", methods=["DELETE"])
def trigger_oauth_expires_delete(triggerid):
    """ Delete a trigger_identity for the bunq_oauth_expires trigger """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return event.trigger_oauth_expires_delete(triggerid)

@app.route("/ifttt/v1/triggers/nuistics_newimage", methods=["POST"])
def trigger_newimage():
    """ Retrieve nuistics_newimage trigger items """
    # errmsg = check_ifttt_service_key()
    errmsg = check_access_token()
    if errmsg:
        return errmsg, 401
    return event.trigger_newimage()

@app.route("/ifttt/v1/triggers/nuistics_newimage/trigger_identity/<triggerid>",
           methods=["DELETE"])
def trigger_newimage_delete(triggerid):
    """ Delete a trigger_identity for the nuistics_newimage trigger """
    # errmsg = check_ifttt_service_key()
    errmsg = check_access_token()
    if errmsg:
        return errmsg, 401
    return event.trigger_newimage_delete(triggerid)

###############################################################################
# Payment action endpoints
###############################################################################

@app.route("/ifttt/v1/actions/bunq_internal_payment", methods=["POST"])
def ifttt_internal_payment():
    """ Execute an internal payment action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return payment.ifttt_bunq_payment(internal=True, draft=False)

@app.route("/ifttt/v1/actions/bunq_external_payment", methods=["POST"])
def ifttt_external_payment():
    """ Execute an external payment action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return payment.ifttt_bunq_payment(internal=False, draft=False)

@app.route("/ifttt/v1/actions/bunq_draft_payment", methods=["POST"])
def ifttt_draft_payment():
    """ Execute an draft payment action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return payment.ifttt_bunq_payment(internal=False, draft=True)


###############################################################################
# Target balance action endpoints
###############################################################################

@app.route("/ifttt/v1/actions/bunq_target_balance_internal", methods=["POST"])
def ifttt_target_balance_internal():
    """ Execute a target balance internal action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return targetbalance.target_balance_internal()

@app.route("/ifttt/v1/actions/bunq_target_balance_external", methods=["POST"])
def ifttt_target_balance_external():
    """ Execute a target balance external action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return targetbalance.target_balance_external()


###############################################################################
# Change card account action endpoints
###############################################################################

@app.route("/ifttt/v1/actions/bunq_change_card_account", methods=["POST"])
def ifttt_change_card_account():
    """ Execute a change card account action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return card.change_card_account()


###############################################################################
# Request inquiry action endpoints
###############################################################################

@app.route("/ifttt/v1/actions/bunq_request_inquiry", methods=["POST"])
def ifttt_request_inquiry():
    """ Execute a request inquiry action """
    errmsg = check_ifttt_service_key()
    if errmsg:
        return errmsg, 401
    return paymentrequest.request_inquiry()


###############################################################################
# Standalone running
###############################################################################

if __name__ == "__main__":
    app.run(host="localhost", port=18000, debug=True)
