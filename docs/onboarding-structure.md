# Club Onboarding Structure

Based on "Activation Questions UK-IRE.xlsx" and technical repository analysis.

## Core Onboarding Products

The activation questions spreadsheet reveals three main product lines, each with distinct configuration workflows:

### 1. **BRS Teesheet** (Base Product)
Core tee time management system - required for all clubs.

**General Configuration:**
- Facility type, address, country
- Sister course relationships
- Multi-course operation setup
- Install type (new/upgrade), location (remote/onsite)

**Tee Sheet Settings:**
- First/last tee times
- Playing times per 9 holes
- 5-sum player functionality
- Additional tee sheets (simulators, range bays, footgolf, etc.)

**Modules to Enable:**
- Member Module (with Competition Purse, Waiting List sub-options)
- Clubhouse PC Module
- SMS Module
- Green Fee Printer Module
- Visitor Module

**Booking Configuration:**
- Casual booking rules
- Member booking setup
- Visitor booking rates and rules
- Payment & refund settings
- T&Cs editing

**Milestones:**
- Timesheet configured
- Green fees/services/catering modified
- System in active use (bookings placed, financial data added)
- Training complete
- Member booking link on website
- 25 members registered & enabled (for member module)

### 2. **BRS Memberships** (Add-on)
Full membership management system.

**Configuration Areas:**
- Existing software provider & interface requirements
- Member data quality verification
- Member categories and types
- Membership wallets/accounts setup
- Account balance transfers

**Key Decisions:**
- Keep existing software interface running? When to turn off?
- Is member data current?
- Have past members been removed/categorized?

### 3. **BRS Power-Up** (Add-on)
Additional functionality for operations.

**Configuration:**
- Facility type confirmation
- (Further details in spreadsheet - more modules/features likely)

## Technical Onboarding Flow (from code)

1. **Database Initialization** (`brs-teesheet`)
   - Run: `./bin/teesheet init`
   - Creates club-specific MySQL database
   - Initializes base schema

2. **Admin Access** (`brs-teesheet`)
   - Run: `./bin/teesheet update-superusers CLUB_NAME`
   - Creates superuser accounts

3. **Configuration Setup** (`brs-config-api`)
   - Add club config to MongoDB
   - Triggers configuration events on message queue
   - Sets up green fee rates, booking rules, system settings

4. **Admin Portal** (`brs-admin-api`)
   - Setup OpenID Connect authentication
   - Configure role-based permissions
   - Dashboard for multi-environment management

5. **Add-on Module Activation** (conditional)
   - **Members**: `brs-members-module` (PHP/Symfony + Vue)
   - **Facilities**: `brs-facilities-module` (PHP + Vue)
   - **Memberships**: `memberships-api` (C# + Vue)
   - **ePOS**: Point of sale system integration
   - **Payments**: Payment processing integration

## Agent Automation Opportunities

### High-Value Automation
1. **Database initialization** - fully automatable
2. **Superuser creation** - fully automatable
3. **Configuration validation** - check all required fields completed
4. **Module activation** - based on activation questions responses
5. **Milestone tracking** - verify each step completed before proceeding

### Human-in-the-Loop Required
1. **Green fee rate configuration** - business logic
2. **Booking rule design** - requires golf course expertise
3. **Training coordination** - scheduling with staff
4. **Website integration** - may require technical support
5. **Data migration** - from existing software

### Workflow Pattern
```
Sales Activation Form → Agent Reads Answers → Agent Generates Config → Human Reviews → Agent Executes Technical Steps → Agent Tracks Milestones → Human Handles Training/Launch
```

## Key Insights

1. **Modular Architecture**: Base teesheet + add-on modules allows incremental onboarding
2. **Structured Questions**: Activation form already captures decision tree for module enablement
3. **Milestone Tracking**: Clear checkboxes for verification at each stage
4. **Multi-System Coordination**: Requires orchestrating brs-teesheet, brs-config-api, brs-admin-api, and optional modules
5. **No Single Runbook**: Technical steps are tribal knowledge, not documented end-to-end

## Next Steps for Agent Design

1. **Phase 1**: Automate core technical flow (init DB → create superuser → validate config)
2. **Phase 2**: Parse activation questions → generate config files → execute setup
3. **Phase 3**: Add milestone tracking workflow with approval gates
4. **Phase 4**: Extend to add-on modules (memberships, facilities, payments)
