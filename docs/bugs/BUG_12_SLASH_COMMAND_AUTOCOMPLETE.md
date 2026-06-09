# Bug #12: Slash Command Autocomplete Not Appearing

## Status
🔴 **OPEN** - Discovered 2026-06-09

## Severity
**Medium** - UX degradation, but workaround exists

## Summary
Typing "/" in the chat input field does not trigger the skill autocomplete dropdown as intended.

## Expected Behavior
When user types "/" in the message input:
1. Dropdown should appear below the input field
2. Dropdown should show all active skills with descriptions
3. User can navigate with arrow keys
4. User can select skill with Enter or mouse click
5. Skill is automatically invoked on selection

## Actual Behavior
- Typing "/" shows no visual feedback
- No dropdown appears
- No error in console
- Semantic matching still works (can trigger skills via natural language)

## Steps to Reproduce
1. Navigate to http://localhost:3000/chat
2. Click on message input field
3. Type "/"
4. Observe: no dropdown appears

## Environment
- **Frontend**: localhost:3000 (Next.js)
- **Backend**: localhost:8000
- **Browser**: Chrome (via Playwright MCP)
- **User**: admin@test.com

## Investigation Notes

### What Works
- Semantic skill matching (typing "reinstate user" triggers REINSTATE_USER skill)
- Skill execution framework
- Frontend components exist (created in Phase 5, Session 7)

### What's Broken
- Slash command trigger not firing
- Dropdown not rendering

### Possible Causes
1. **Frontend Event Handler**
   - Event listener for "/" keypress not attached
   - React useEffect dependency missing
   - Event bubbling prevented

2. **API Endpoint**
   - `/api/skills` endpoint not returning data
   - Backend not responding with skill list
   - API permissions blocking request

3. **State Management**
   - React state for `showSkillDropdown` not updating
   - Conditional rendering logic broken
   - Component not re-rendering

4. **Z-Index / CSS**
   - Dropdown rendering but hidden behind other elements
   - CSS display property incorrect
   - Positioning off-screen

## Files to Check
- `frontend/src/components/chat/ChatInput.tsx` - Input handling
- `frontend/src/components/chat/SkillAutocomplete.tsx` - Dropdown component
- `frontend/src/hooks/useSkillAutocomplete.ts` - Hook logic (if exists)
- `backend/routes/skills.py` - Skills list endpoint

## Workaround
Users can still trigger skills via semantic matching by typing natural language:
- "I need to reinstate a user" → triggers REINSTATE_USER
- "create a booking" → would trigger booking skill

## Impact
- **Users**: Cannot discover available skills via UI
- **UX**: Must rely on documentation or guessing
- **Adoption**: Harder for new users to learn system

## Related Work
- **Phase 5, Session 7**: Slash command feature implemented
- **Phase 5 Handover**: Listed as "✅ **Slash command detection**" under completed features

## Fix Priority
**Medium** - Should be fixed before production, but not blocking

## Proposed Fix
1. Debug frontend event handling for "/" input
2. Verify `/api/skills` API endpoint returns data
3. Check React DevTools for state changes
4. Add console logging to trace execution path
5. Test dropdown rendering in isolation

## Testing Plan
After fix:
1. Type "/" → dropdown appears
2. Arrow keys navigate skills
3. Enter key selects skill
4. Mouse click selects skill
5. ESC key closes dropdown
6. Clicking outside closes dropdown

## Notes
- This was working in Phase 5 Session 7 according to handover doc
- Regression may have occurred in later changes
- Need to review git history for changes to chat input handling
