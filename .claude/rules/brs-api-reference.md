# BRS Teesheet API Reference

## API Documentation URLs

When BRS API calls fail during testing, consult these documentation endpoints:

| API | URL | Description |
|-----|-----|-------------|
| Main API | http://localhost:8056/api/documentation/ | Primary teesheet API docs (Swagger) |
| Admin API | http://localhost:8056/api/admin/documentation/ | Administrative endpoints |
| GolfNow G1 API | http://localhost:8056/api/g1/documentation/ | GolfNow integration API |

## When to Use

Reference these docs when:
- API returns 400 "Validation Failed"
- Unknown field format required
- Missing required parameters
- Authentication issues

## Known Issues

### Booking Creation (v3)
The `POST /api/v3/clubs/{clubId}/bookings` endpoint returns "Validation Failed" with empty error arrays when:
1. **Missing `tee_sheet_booking` wrapper** - Symfony form expects data wrapped in this key
2. Missing `player.type` field (must be "MEMBER" or "CONTACT")
3. Missing `player.id` for MEMBER/CONTACT types
4. The tee time doesn't exist on the specified course/date/time
5. The club's tee sheet is not configured

**Root Cause (Form Binding):**
- FOSRestBundle's BodyListener decodes JSON into `$request->request` parameters
- Symfony's `handleRequest()` checks if the request "matches" the form by looking for the form's block prefix: `tee_sheet_booking`
- If JSON structure doesn't include this wrapper, `isSubmitted()` returns false and you get empty error arrays

**Correct Request Format:**
```json
{
  "tee_sheet_booking": {
    "course_id": 1,
    "date": "2026-05-28",
    "time": "09:00",
    "holes": 18,
    "reservation_name": "Test Booking",
    "reservation_type": "Visitor",
    "slots": {
      "1": {
        "player": {
          "type": "MEMBER",
          "id": 17,
          "name_on_tee_sheet": "A Kotecha"
        }
      }
    }
  }
}
```

**Player Type Requirements:**
- `type`: Must be "GUEST", "MEMBER", or "CONTACT" (uppercase)
- `id`: Required for MEMBER and CONTACT types, NOT required for GUEST
- `name_on_tee_sheet`: Display name on the tee sheet
- For visitor bookings, use GUEST type (no id needed)

### Test Club Issues
- `testclub1779893558` has **no tee times configured** - booking creation will always fail
- Use `brsgolfclubsales` for testing booking workflows

## Booking Endpoints

### v3 Bookings (preferred for agent)
- `POST /api/v3/clubs/{clubId}/bookings` - Create booking
- `GET /api/v3/clubs/{clubId}/bookings` - List bookings (requires start_date)
- `POST /api/v3/clubs/{clubId}/bookings/batch` - Batch create bookings
- `PATCH /api/v3/clubs/{clubId}/bookings/{booking}` - Update booking
- `DELETE /api/v3/clubs/{clubId}/bookings/{booking}` - Delete booking

### v2 Bookings
- `POST /api/v2/clubs/{clubId}/bookings.json` - Create booking
- `POST /api/v2/clubs/{clubId}/bookings/{booking}/cancel.json` - Cancel booking
- `POST /api/v2/clubs/{clubId}/members/{member}/bookings.json` - Create member booking

### v2 Member Bookings
- `GET /api/v2/clubs/{clubId}/members/{member}/bookings.json` - Get member bookings
- `POST /api/v2/clubs/{clubId}/members/{member}/bookings.json` - Create member booking
- `PUT /api/v2/clubs/{clubId}/members/{member}/bookings.json` - Edit member booking

## Green Fee Endpoints

### v3 Visitor Green Fees
- `POST /api/v3/clubs/{clubId}/visitor-green-fee-rates.json` - Create green fee rate
- `GET /api/v3/clubs/{clubId}/visitor-green-fee-rates` - List green fee rates
- `PATCH /api/v3/clubs/{clubId}/visitor-green-fee-rates/{id}.json` - Update rate

### v3 Green Fee Lookups
- `GET /api/v3/clubs/{clubId}/green-fees` - List active green fees
- `GET /api/v3/clubs/{clubId}/member-green-fees` - Member green fee rates
- `GET /api/v3/clubs/{clubId}/member/guest/green-fees` - Guest green fees

## Tee Sheet Endpoints
- `GET /api/v3/clubs/{clubId}/teesheets/` - Full teesheet data
- `GET /api/v2/clubs/{clubId}/courses/{courseId}/teesheets/{date}.json` - Tee sheet for date
- `POST /api/v3/clubs/{clubId}/tee-times/reserve` - Reserve tee times
- `POST /api/v3/clubs/{clubId}/squeeze-tee-time` - Create squeezed tee time

## Authentication
- `POST /{clubId}/oauth/v2/token` - Get OAuth token
- Required: client_id, client_secret, grant_type, api_key
- Grant type: `http://www.brsgolf.com/grants/api_key`

## Troubleshooting

If validation fails with empty error arrays:
1. Check the Swagger docs for exact field format
2. Verify all required nested structures
3. Check if endpoint requires specific content type
4. Try the interactive Swagger UI to test payloads
