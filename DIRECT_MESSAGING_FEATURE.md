# Direct Messaging Feature Documentation

## Overview
Added direct messaging capability between admin ↔ curator roles with ID/name lookup and user list display.

## Features Implemented

### 1. Admin → Curator Direct Messaging

**Button:** "Написать куратору" (Write to curator)
- **Location:** Main admin keyboard
- **FSM States:** `DirectMessageStates` (waiting_curator_query, waiting_text, waiting_confirm)

**Flow:**
1. Admin clicks "Написать куратору" button
2. Bot displays list of all curators with their ID, name, and username (@handle)
3. Admin searches by:
   - Exact ID match (e.g., "12345")
   - Partial name match (e.g., "Ivan")
   - Partial username match (e.g., "@ivan")
4. If multiple matches found, admin selects exact ID
5. Admin writes message text
6. Bot shows preview
7. Admin confirms "Отправить" (Send)
8. Message sent to curator with header:
   ```
   📨 От администратора:
   ID: <code>ADMIN_ID</code>
   Имя: Admin Name
   
   [message text]
   ```

### 2. Curator → Admin Direct Messaging

**Button:** "Ответить администратору" (Reply to admin)
- **Location:** Main curator keyboard
- **FSM States:** `DirectMessageStates` (waiting_admin_id, waiting_text, waiting_confirm)

**Flow:**
1. Curator clicks "Ответить администратору" button
2. Bot asks for admin ID (curators must know admin ID)
3. Bot verifies admin ID exists in .env ADMINS list
4. Curator writes message text
5. Bot shows preview
6. Curator confirms "Отправить" (Send)
7. Message sent to admin with header:
   ```
   📨 От куратора:
   ID: <code>CURATOR_ID</code>
   Имя: Curator Name
   
   [message text]
   ```

## Technical Details

### Database
- No new DB columns needed
- Uses existing user records to fetch curator/admin info

### FSM States

**admin.py - DirectMessageStates:**
```python
class DirectMessageStates(StatesGroup):
    waiting_curator_query = State()  # Search by ID or name
    waiting_text = State()
    waiting_confirm = State()
```

**curator.py - DirectMessageStates:**
```python
class DirectMessageStates(StatesGroup):
    waiting_admin_id = State()
    waiting_text = State()
    waiting_confirm = State()
```

### Handlers Added

**admin.py:**
- `msg_admin_direct_to_curator()` - Show curator list
- `direct_message_curator_query()` - Search by ID/name
- `direct_message_curator_text()` - Accept message text
- `direct_message_curator_confirm()` - Send message

**curator.py:**
- `msg_direct_to_admin()` - Initiate PM to admin
- `direct_message_admin_id()` - Accept admin ID
- `direct_message_admin_text()` - Accept message text
- `direct_message_admin_confirm()` - Send message

### Keyboard Updates

**admin.py keyboard:**
Added "Написать куратору" button between broadcast buttons and admin panel button

**curator.py keyboard:**
Added "Ответить администратору" button above settings/admin buttons

## Security Considerations

1. **Admin → Curator:** Bot fetches curator list from DB and .env
2. **Curator → Admin:** Curator must provide exact admin ID, bot validates against .env
3. **All messages:** Sender info (ID, name) included for transparency
4. **Authorization:** Role checks before allowing message initiation
5. **Authentication:** Buttons require an active session (2-minute window); if 2FA is enabled, the password/2FA flow runs before messaging.

## Messages Format

Both directions follow format:
```
📨 [Роль]:
ID: <code>SENDER_ID</code>
Имя: Sender Name

Message content here
```

This format:
- Clearly identifies sender role
- Shows sender ID in monospace for easy reference
- Shows sender name for human identification
- Separates metadata from actual message content

## Testing Checklist

- [x] Admin can see curator list with ID, name, username
- [x] Admin can search curator by ID (exact match)
- [x] Admin can search curator by name (partial match)
- [x] Admin can search curator by username (partial match)
- [x] Multiple matches prompt for exact ID selection
- [x] Message preview shown before sending
- [x] Message sent with proper header format
- [x] Curator receives message with admin info
- [x] Curator can initiate PM to admin by entering ID
- [x] Bot validates admin ID against .env settings
- [x] Message preview shown before sending
- [x] Message sent with proper header format
- [x] Admin receives message with curator info
- [x] Cancel button works at all FSM stages
- [x] Returns to proper keyboard after completion/cancellation

## Future Enhancements

1. Add admin list display for curators (currently requires manual ID entry)
2. Add message history/logging
3. Add pagination for large curator lists
4. Add search by group (for admin browsing curators by group)
5. Add message delivery confirmation
