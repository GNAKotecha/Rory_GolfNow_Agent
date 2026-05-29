1) How visitor bookings are created (brs-visitors-module -> brs-teesheet)
High-level flow used by the visitors app:

Load config/courses/visitor teesheets
User picks tee time and rate
Lock tee time
Build checkout payload
Create/find contact
Create booking in teesheet
Take payment (or pay-at-course path)
Patch payment details onto booking
Unlock/delete locks
The visitors app calls:

POST /api/checkout/prepare
POST /api/checkout/complete
POST /api/checkout/completepayatcourse
POST /api/checkout/cancel
Internally, booking creation goes to teesheet:

POST /api/v3/clubs/{clubId}/bookings
body root key is tee_sheet_booking

Visitor checkout request shape (what your agent must produce first)
From checkout model + Vue store state, main fields are:

teeTime: required
bookingType: required
date: required
players: required map (keys 1..N)
course
holes
greenFee
marketing
openCompetition
card
packageDescription
Player object includes:

first_name, last_name
type (Visitor/Member)
club, handicap, cdh
email, telephone, mobile
address fields
notes
has_buggy
Business validations in visitor flow
Your agent should expect failures unless these are satisfied:

At least 1 player
Booking type must be one of: open competition, golf only, package
Tee time must still exist at chosen date/time
If tee time has fixed holes, must match selected rate holes
Mixed member/visitor team rules apply for open competitions
AMEX can be blocked by club config
Booking amount must be non-zero
Tee time lock must be obtained first
What is actually posted to teesheet booking API
Visitors module maps checkout -> tee_sheet_booking with fields like:

course_id
date (yyyy-mm-dd)
time (hh:mm)
holes (9 or 18)
reservation_name (from first player)
reservation_type = Visitor
contact_id
notes: booking/payment/club
slots map:
each slot has player object and green_fee object
player contains name_on_tee_sheet, type (GUEST), club, handicap, cdh, has_buggy
green_fee contains agreed_price and description
payments (empty at create; patched later after payment confirmation)
Headers influencing behavior:

x-brs-visitor-source (optional source tagging)
is-open-comp-booking (optional)
x-brs-visitor (used in teesheet side logic for visitor context)
2) How bookings are created in brs-teesheet
You effectively have 3 relevant create paths:

Staff booking create
POST /api/v2/bookings
root form key: booking_request
Member booking create/edit
POST /api/v2/members/{member}/bookings
PUT /api/v2/members/{member}/bookings
root form key: member_booking_request
Teesheet booking create (used by visitors module)
POST /api/v3/.../bookings (club-scoped route in this codebase)
root body key: tee_sheet_booking
A) v2 booking_request fields (staff booking flow)
Top-level:

contact_id (optional)
notes (optional)
additional_items (optional)
tee_times (required, exactly 1 item)
tee_times[0]:

course_id: required, allowed values include 1/2/3/5
date: required yyyy-mm-dd
time: required hh:mm
type: optional reservation type (must resolve to valid reservation type)
title: optional, max length 50
no_of_buggies: optional
slots: required, min 1 max 4
slots[i]:

holes: 9 or 18
name_on_teesheet and/or user_id/contact_id needed (cannot be empty slot)
green_fee_rate_id optional (often required in real rules)
optional flags like force_rate
validations include existing tee time, valid user ids, consistent holes rules, etc.
B) v2 member_booking_request fields (member flow)
Top-level:

course_id: required, one of 1/2/3/5
date: required yyyy-mm-dd
time: required hh:mm
slots: required, min 1 max 4
stripe_payment.vendor_tx_code optional
Each slots[i]:

holes: required, 9 or 18
type: one of
NONE
GUEST_WITH
RESERVED_BY
MEMBER
MEMBER_WITH
FREE_TEXT
user_id optional (validated if provided)
rate optional
has_buggy / buggy optional
Observed behavior from tests:

unknown fields are rejected
invalid course/date/time/type rejected
non-existing tee time rejected
duplicate create on same tee time can conflict
auth matters (staff/admin works; member permissions are constrained by authorization checks)
C) v3 tee_sheet_booking fields (visitors path)
Based on BookingType + SlotType + PlayerType + GreenFeeType:

Top-level commonly used:

course_id (required)
date (required)
time (required)
holes (required 9/18)
reservation_name (optional but practically used)
reservation_type (optional but used by visitors flow)
contact_id (optional)
number_of_buggies (optional)
caddy_requested (optional)
notes (optional)
slots (optional by form, but needed to create a meaningful booking)
payments (optional)
slots[i]:

player (required in slot):
id optional
type required
name_on_tee_sheet optional depending type/rules
club/handicap/cdh optional/conditional
arrived optional
has_buggy/buggy optional
green_fee optional:
id or description/agreed_price depending validation path
3) What an NL-to-booking agent should extract
Minimum slot-filling schema:

booking_actor: visitor or member
target_member_id (required for member bookings endpoint)
course_id
date
time
holes
party_size
players:
name
role/type (member/guest/visitor)
member id when applicable
handicap/club/cdh when needed
buggy preference
rate intent:
green fee id OR package/golf-only intent
payment mode:
pay now vs pay at course
notes
contact details for lead player (visitor flow)
Recommended orchestration for the agent
Parse intent and entities from natural language
Resolve missing required fields with follow-up questions
Fetch tee sheet availability and valid rates first
Validate course/date/time/holes against available tee time
Build normalized internal booking object
Convert to endpoint-specific payload:
visitor checkout payload for visitors flow
member_booking_request for member flow
booking_request or tee_sheet_booking for staff flow
Lock tee time before create where required
Submit
Handle common failures with automatic repair prompts:
invalid type
no such tee time
slot count/holes mismatch
invalid member id
conflict/lock
4) Practical payload templates for your agent
Visitor create path (conceptual):

Build checkout payload with teeTime, date, bookingType, players, course, holes, greenFee, marketing
Call visitors checkout prepare/complete flow
Let visitors module map and post tee_sheet_booking internally
Member create path (direct teesheet API):

member_booking_request:
course_id, date, time
slots[1..n]:
holes
type
user_id where member slot
optional rate/buggy fields
Staff generic booking path:

booking_request:
tee_times[0]: course_id/date/time/type/title/no_of_buggies/slots
optional notes, contact_id, additional_items