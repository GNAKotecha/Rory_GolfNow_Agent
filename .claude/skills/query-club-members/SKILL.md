---
name: query-club-members
version: 1.0.0
type: task
description: Search and display club members from BRS database with filters
triggers:
  - "find members in"
  - "search for members"
  - "list members"
  - "show club members"
  - "query members"
inputs:
  required:
    - club_identifier: Club name or ID
  optional:
    - name_filter: First or last name to match
    - email_filter: Email pattern to search
    - usergroup_filter: Filter by usergroup
    - limit: Maximum results (default 20)
workflow:
  1: "Parse user query to extract club identifier and filters"
  2: "Query database for club ID if name provided"
  3: "Build SQL query with appropriate WHERE clauses"
  4: "Execute run_sql tool with parameterized query"
  5: "Format results in readable table"
  6: "Return member count and details"
tools:
  - run_sql (database queries)
error_handling:
  1: "Club not found → Search by partial name match, suggest alternatives"
  2: "No members found → Confirm filters, suggest broadening search"
  3: "SQL error → Log error, return user-friendly message"
output_format: |
  Found X members in [Club Name]:
  
  | ID | Username | Email | Name | User Group |
  |----|----------|-------|------|------------|
  | ... | ... | ... | ... | ... |
  
  Filters applied: [list filters]
---

# Query Club Members

## Purpose
Enable easy search and discovery of club members from the BRS database with flexible filtering options.

## Notes
- Supports search by club name or ID
- Allows filtering by name, email, or usergroup
- Returns formatted table with essential member information
- Handles partial matches for flexible queries
