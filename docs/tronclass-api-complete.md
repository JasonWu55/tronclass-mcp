# TronClass API Documentation

Generated from:
- live authentication and endpoint verification against https://elearn2.fju.edu.tw
- frontend bundle endpoint extraction (251 endpoint patterns, 204 with inferred methods)
- MCP server implementation and tests in this repository

Saved by Hermes on behalf of the user.

## 1. Overview

Base URL: https://elearn2.fju.edu.tw

TronClass uses a CAS-based login flow followed by an application session exchange. After login, application APIs are primarily accessed under /api/* with the X-SESSION-ID header and session cookie.

## 2. Authentication Flow

### Step 1: POST /cas/v1/tickets

- Expected status: 201
- Notes: Returns Location header with TGT. In live traffic the Location came back as http:// and had to be normalized to https:// before step 2.

### Step 2: POST /cas/v1/tickets/{TGT}

- Expected status: 200
- Notes: Returns plain-text service ticket (ST-...).

### Step 3: GET /api/cas-login?ticket={ST}

- Expected status: 200
- Notes: Returns JSON user payload and X-SESSION-ID header used for subsequent API calls.

### Required headers observed during app API requests

- x-session-id: value returned by /api/cas-login
- X-Requested-With: XMLHttpRequest
- Origin: capacitor://localhost
- Accept: application/json, text/plain, */*
- User-Agent: TronClass mobile/common user agent works well

## 3. Verified Endpoints

### GET /api/todos

- Verified status: 200
- Response shape: todo_list[]
- Notes: Live verified; returned 33 todos.

### GET /api/my-courses

- Verified status: 200
- Response shape: courses[]
- Notes: Live verified; returned 22 courses.

### GET /api/my-semesters

- Verified status: 200
- Response shape: semesters[]
- Notes: Live verified; returned 2 semesters.

### GET /api/calendar-events

- Verified status: 200
- Response shape: events[]
- Notes: Live verified; returned empty list for this account at test time.

### GET /api/notes

- Verified status: 200
- Response shape: notes[]
- Notes: Live verified with and without course_id.

### GET /api/grades

- Verified status: 200
- Response shape: grades[]
- Notes: Live verified with course_id parameter.

### GET /api/resource-groups

- Verified status: 200
- Response shape: resource_groups[]
- Notes: Live verified with course_id parameter.

### GET /api/user/recently-visited-courses

- Verified status: 200
- Response shape: visited_courses[]
- Notes: Live verified.

## 4. Authentication / Behavior Notes

- Most application API calls require x-session-id plus the session cookie from /api/cas-login.
- The initial TGT Location header used http:// in live testing; converting it to https:// was required before exchanging TGT for ST.
- Some discovered endpoints are role-specific or require path segments rather than query params; calling them with guessed params often produced 404 or 403.
- A few frontend-discovered endpoints returned server errors when invoked without the exact UI payload shape (for example /api/org-bulletin/bulletins).

## 5. Endpoint Group Summary

- Total discovered endpoint patterns: 251
- Total discovered endpoint patterns with inferred methods: 204
- Total endpoint groups: 110

### academic-years

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/academic-years?fields=id

### activies

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/activies/classin/join-url

### activities

- Endpoint count: 6
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/activities
  - /api/activities/
  - /api/activities/classin/webcast-url
  - /api/activities/delete-check?activity_id=
  - /api/activities/have-dependents

### activity

- Endpoint count: 2
- Methods seen: GET
- Sample URLs:
  - /api/activity/
  - /api/activity/cloud-classroom?start=

### activity-resort

- Endpoint count: 1
- Methods seen: PUT
- Sample URLs:
  - /api/activity-resort

### ai-ppt

- Endpoint count: 2
- Methods seen: GET, POST
- Sample URLs:
  - /api/ai-ppt/usage
  - /api/ai-ppt/user/usage/count

### air-credit

- Endpoint count: 6
- Methods seen: GET
- Sample URLs:
  - /api/air-credit/audits
  - /api/air-credit/course
  - /api/air-credit/resources/
  - /api/air-credit/user
  - /api/air-credit/user/courses/ai-ability

### all-orgs

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/all-orgs

### angular.element

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/angular.element

### ask-questions

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/ask-questions/

### auth_code

- Endpoint count: 3
- Methods seen: GET, POST
- Sample URLs:
  - /api/auth_code/auth_validate
  - /api/auth_code/get_auth_code
  - /api/auth_code/validate_auth_code

### authz

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/authz/course-roles

### blobstorage

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/blobstorage/open-client-url?parent_id=

### blueprint

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/blueprint/

### bulletins

- Endpoint count: 1
- Methods seen: POST
- Sample URLs:
  - /api/bulletins/

### calendar-alerts

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/calendar-alerts?no-intercept=true

### calendar-events

- Endpoint count: 4
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/calendar-events
  - /api/calendar-events/
  - /api/calendar-events/users/
  - /api/calendar-events?no-intercept=true

### calendar-meeting

- Endpoint count: 2
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/calendar-meeting
  - /api/calendar-meeting/

### calendar-timetables

- Endpoint count: 3
- Methods seen: GET, POST, PUT
- Sample URLs:
  - /api/calendar-timetables
  - /api/calendar-timetables/
  - /api/calendar-timetables?no-intercept=true

### captures

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/captures/

### cc-license

- Endpoint count: 2
- Methods seen: GET
- Sample URLs:
  - /api/cc-license/groups
  - /api/cc-license/map

### certifications

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/certifications

### chinamcloud

- Endpoint count: 2
- Methods seen: POST
- Sample URLs:
  - /api/chinamcloud/resources
  - /api/chinamcloud/upload

### classes

- Endpoint count: 2
- Methods seen: unknown
- Sample URLs:
  - /api/classes
  - /api/classes?org_id=

### classrooms

- Endpoint count: 1
- Methods seen: DELETE
- Sample URLs:
  - /api/classrooms/

### combine-courses

- Endpoint count: 2
- Methods seen: GET, POST
- Sample URLs:
  - /api/combine-courses
  - /api/combine-courses/

### completion-criteria

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/completion-criteria

### config

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/config?no-intercept=true

### copy-third-part-resources

- Endpoint count: 1
- Methods seen: POST
- Sample URLs:
  - /api/copy-third-part-resources

### course

- Endpoint count: 11
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/course
  - /api/course/
  - /api/course/access-code/
  - /api/course/activities-read/
  - /api/course/activities-read/exam/

### course-classifications

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/course-classifications

### course-estimates

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/course-estimates/

### courses

- Endpoint count: 11
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/courses/
  - /api/courses/count
  - /api/courses/interactions/
  - /api/courses/interactions/vote/
  - /api/courses/lecture-live-activity/

### courseware-quiz

- Endpoint count: 6
- Methods seen: GET, POST, PUT
- Sample URLs:
  - /api/courseware-quiz/activity/
  - /api/courseware-quiz/format-question
  - /api/courseware-quiz/generate-subjects
  - /api/courseware-quiz/generate-subjects-by-text
  - /api/courseware-quiz/quiz/

### curriculum-classifications

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/curriculum-classifications

### data-import

- Endpoint count: 12
- Methods seen: POST
- Sample URLs:
  - /api/data-import/chaoxing-score/
  - /api/data-import/course-groups
  - /api/data-import/course/
  - /api/data-import/courses
  - /api/data-import/edit-courses

### departments

- Endpoint count: 4
- Methods seen: GET
- Sample URLs:
  - /api/departments
  - /api/departments/
  - /api/departments?
  - /api/departments?no-intercept=true

### ding-talk

- Endpoint count: 2
- Methods seen: GET, PUT
- Sample URLs:
  - /api/ding-talk/chat?course_id=
  - /api/ding-talk/user-id

### dingtalk-lives

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/dingtalk-lives/

### entries

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/entries

### exam

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/exam/

### exams

- Endpoint count: 2
- Methods seen: DELETE, POST
- Sample URLs:
  - /api/exams/
  - /api/exams/batch_delete

### grades

- Endpoint count: 2
- Methods seen: unknown
- Sample URLs:
  - /api/grades
  - /api/grades?org_id=

### grant

- Endpoint count: 2
- Methods seen: unknown
- Sample URLs:
  - /api/grant/code/
  - /api/grant/code?uid=

### group-sets

- Endpoint count: 1
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/group-sets/

### groups

- Endpoint count: 1
- Methods seen: DELETE, PUT
- Sample URLs:
  - /api/groups/

### h5-courseware

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/h5-courseware/

### homework

- Endpoint count: 1
- Methods seen: GET, PUT
- Sample URLs:
  - /api/homework/

### instruction-team

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/instruction-team/meeting

### invites

- Endpoint count: 1
- Methods seen: GET, POST
- Sample URLs:
  - /api/invites/

### knowledge-capture-visit

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/knowledge-capture-visit

### knowledge-graph

- Endpoint count: 4
- Methods seen: GET, POST
- Sample URLs:
  - /api/knowledge-graph/courses/
  - /api/knowledge-graph/forest-versions/-/stats:batchGet
  - /api/knowledge-graph/kfs-courses/-/published-forest-versions:batchGet
  - /api/knowledge-graph/kfs-subjects

### knowledge-node

- Endpoint count: 1
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/knowledge-node/

### knowledge-nodes

- Endpoint count: 2
- Methods seen: GET, POST
- Sample URLs:
  - /api/knowledge-nodes/
  - /api/knowledge-nodes/parse/docx

### knowledge-resource-visit

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/knowledge-resource-visit

### lark

- Endpoint count: 2
- Methods seen: GET
- Sample URLs:
  - /api/lark/authorization/check
  - /api/lark/files

### lecture-live

- Endpoint count: 2
- Methods seen: POST
- Sample URLs:
  - /api/lecture-live/schedule/
  - /api/lecture-live?jwt=

### lesson-resources

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/lesson-resources/shared-stat

### live-records

- Endpoint count: 1
- Methods seen: GET, POST
- Sample URLs:
  - /api/live-records/

### management

- Endpoint count: 2
- Methods seen: POST
- Sample URLs:
  - /api/management/calendar-meeting/excel
  - /api/management/calendar-meeting?page=

### meeting

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/meeting/

### modules

- Endpoint count: 1
- Methods seen: PUT
- Sample URLs:
  - /api/modules/

### my-academic-years

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/my-academic-years?fields=id

### my-captures

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/my-captures

### my-courses

- Endpoint count: 1
- Methods seen: POST
- Sample URLs:
  - /api/my-courses

### my-curriculum-academic-years

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/my-curriculum-academic-years?fields=id

### my-curriculum-semesters

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/my-curriculum-semesters?

### my-semesters

- Endpoint count: 2
- Methods seen: GET
- Sample URLs:
  - /api/my-semesters
  - /api/my-semesters?

### my-semesters-all

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/my-semesters-all

### ng.

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/ng.

### ngSanitize

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/ngSanitize

### notes

- Endpoint count: 3
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/notes
  - /api/notes/
  - /api/notes?course_id=

### obe

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/obe/existed-metrics?params=

### online-videos

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/online-videos/

### org

- Endpoint count: 2
- Methods seen: GET
- Sample URLs:
  - /api/org
  - /api/org/

### org-bulletin

- Endpoint count: 4
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/org-bulletin/bulletins
  - /api/org-bulletin/bulletins/
  - /api/org-bulletin/bulletins?fields=id
  - /api/org-bulletin/classifications

### orgs

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/orgs/

### outline

- Endpoint count: 1
- Methods seen: POST
- Sample URLs:
  - /api/outline/notify

### program

- Endpoint count: 2
- Methods seen: unknown
- Sample URLs:
  - /api/program/course-programs?department_ids=
  - /api/program/user-programs?fields=

### public-captures

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/public-captures

### public-resources

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/public-resources

### questionnaires

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/questionnaires/

### resource-file

- Endpoint count: 2
- Methods seen: GET
- Sample URLs:
  - /api/resource-file/
  - /api/resource-file/org/arrears/

### resource-group

- Endpoint count: 2
- Methods seen: DELETE, POST, PUT
- Sample URLs:
  - /api/resource-group
  - /api/resource-group/

### resource-groups

- Endpoint count: 5
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/resource-groups
  - /api/resource-groups/
  - /api/resource-groups/folders
  - /api/resource-groups/resources
  - /api/resource-groups?page=

### resources

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/resources/

### rollcall

- Endpoint count: 3
- Methods seen: POST, PUT
- Sample URLs:
  - /api/rollcall/
  - /api/rollcall/merged-rollcall
  - /api/rollcall/merged-rollcall/student-rollcalls

### semesters

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/semesters

### shared-resource

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/shared-resource/classifications

### shared-resources

- Endpoint count: 5
- Methods seen: DELETE, GET
- Sample URLs:
  - /api/shared-resources/
  - /api/shared-resources/management
  - /api/shared-resources/stat
  - /api/shared-resources/stat/video-resources
  - /api/shared-resources/stat/video-resources/export

### slides

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/slides?keyword=

### stat

- Endpoint count: 9
- Methods seen: GET, POST
- Sample URLs:
  - /api/stat/activities-for-courses
  - /api/stat/attendance/export/to/
  - /api/stat/courses/
  - /api/stat/courses/class-hours/export
  - /api/stat/courses/export/to/

### statistic

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/statistic

### subject-libs

- Endpoint count: 1
- Methods seen: DELETE
- Sample URLs:
  - /api/subject-libs/

### submissions

- Endpoint count: 1
- Methods seen: GET, POST
- Sample URLs:
  - /api/submissions/

### syllabus

- Endpoint count: 1
- Methods seen: PUT
- Sample URLs:
  - /api/syllabus/

### tencent_meeting

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/tencent_meeting/check-user-auth

### toggle-opened-orgs

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/toggle-opened-orgs?toggle=org_team_teaching

### top-departments

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/top-departments?fields=

### uploads

- Endpoint count: 15
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/uploads
  - /api/uploads/
  - /api/uploads/audio/
  - /api/uploads/batch/blob
  - /api/uploads/details/query

### uptoken

- Endpoint count: 1
- Methods seen: GET
- Sample URLs:
  - /api/uptoken?id=

### user

- Endpoint count: 21
- Methods seen: GET, POST, PUT
- Sample URLs:
  - /api/user/academic-learning-resources
  - /api/user/association-code
  - /api/user/chat
  - /api/user/check-expired-password
  - /api/user/classes

### user-actions

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/user-actions?jwt=

### user-visits

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/user-visits

### users

- Endpoint count: 2
- Methods seen: GET, POST
- Sample URLs:
  - /api/users/
  - /api/users?page=

### video-quizzes

- Endpoint count: 2
- Methods seen: GET
- Sample URLs:
  - /api/video-quizzes/
  - /api/video-quizzes/org/arrears/

### virtual-classroom-resources

- Endpoint count: 1
- Methods seen: GET, POST
- Sample URLs:
  - /api/virtual-classroom-resources

### vtrses

- Endpoint count: 4
- Methods seen: DELETE, GET, POST, PUT
- Sample URLs:
  - /api/vtrses
  - /api/vtrses/
  - /api/vtrses/resources/classifications/
  - /api/vtrses/share-resources

### warning

- Endpoint count: 1
- Methods seen: PUT
- Sample URLs:
  - /api/warning/student/

### wedrive

- Endpoint count: 1
- Methods seen: unknown
- Sample URLs:
  - /api/wedrive/files?page=

## 6. Full Endpoint Catalog

### academic-years

- /api/academic-years?fields=id [unknown]

### activies

- /api/activies/classin/join-url [GET]

### activities

- /api/activities [DELETE]
- /api/activities/ [DELETE, GET, POST, PUT]
- /api/activities/classin/webcast-url [GET]
- /api/activities/delete-check?activity_id= [GET]
- /api/activities/have-dependents [GET]
- /api/activities/resources/ [POST]

### activity

- /api/activity/ [GET]
- /api/activity/cloud-classroom?start= [GET]

### activity-resort

- /api/activity-resort [PUT]

### ai-ppt

- /api/ai-ppt/usage [POST]
- /api/ai-ppt/user/usage/count [GET]

### air-credit

- /api/air-credit/audits [GET]
- /api/air-credit/course [GET]
- /api/air-credit/resources/ [GET]
- /api/air-credit/user [GET]
- /api/air-credit/user/courses/ai-ability [GET]
- /api/air-credit/user/token [GET]

### all-orgs

- /api/all-orgs [unknown]

### angular.element

- /api/angular.element [unknown]

### ask-questions

- /api/ask-questions/ [unknown]

### auth_code

- /api/auth_code/auth_validate [GET]
- /api/auth_code/get_auth_code [POST]
- /api/auth_code/validate_auth_code [POST]

### authz

- /api/authz/course-roles [GET]

### blobstorage

- /api/blobstorage/open-client-url?parent_id= [unknown]

### blueprint

- /api/blueprint/ [GET]

### bulletins

- /api/bulletins/ [POST]

### calendar-alerts

- /api/calendar-alerts?no-intercept=true [GET]

### calendar-events

- /api/calendar-events [POST]
- /api/calendar-events/ [DELETE, PUT]
- /api/calendar-events/users/ [unknown]
- /api/calendar-events?no-intercept=true [GET]

### calendar-meeting

- /api/calendar-meeting [GET, POST]
- /api/calendar-meeting/ [DELETE, PUT]

### calendar-timetables

- /api/calendar-timetables [POST]
- /api/calendar-timetables/ [PUT]
- /api/calendar-timetables?no-intercept=true [GET]

### captures

- /api/captures/ [GET]

### cc-license

- /api/cc-license/groups [unknown]
- /api/cc-license/map [GET]

### certifications

- /api/certifications [GET]

### chinamcloud

- /api/chinamcloud/resources [unknown]
- /api/chinamcloud/upload [POST]

### classes

- /api/classes [unknown]
- /api/classes?org_id= [unknown]

### classrooms

- /api/classrooms/ [DELETE]

### combine-courses

- /api/combine-courses [GET, POST]
- /api/combine-courses/ [GET, POST]

### completion-criteria

- /api/completion-criteria [GET]

### config

- /api/config?no-intercept=true [GET]

### copy-third-part-resources

- /api/copy-third-part-resources [POST]

### course

- /api/course [POST]
- /api/course/ [DELETE, GET, POST, PUT]
- /api/course/access-code/ [GET]
- /api/course/activities-read/ [POST]
- /api/course/activities-read/exam/ [unknown]
- /api/course/activities/ [GET, PUT]
- /api/course/bulletins/ [DELETE, PUT]
- /api/course/custom-score-items/ [DELETE, PUT]
- /api/course/enrollments [DELETE, PUT]
- /api/course/enrollments/ [DELETE, PUT]
- /api/course/mbz/import [POST]

### course-classifications

- /api/course-classifications [GET]

### course-estimates

- /api/course-estimates/ [GET]

### courses

- /api/courses/ [DELETE, GET, POST, PUT]
- /api/courses/count [GET]
- /api/courses/interactions/ [PUT]
- /api/courses/interactions/vote/ [PUT]
- /api/courses/lecture-live-activity/ [POST]
- /api/courses/settings [PUT]
- /api/courses/statistic/resource-audit [GET]
- /api/courses/sync_from_urp [POST]
- /api/courses/tencent-meeting/activities [POST]
- /api/courses/tpdoe/stat-students? [GET]
- /api/courses?page= [POST]

### courseware-quiz

- /api/courseware-quiz/activity/ [GET, POST]
- /api/courseware-quiz/format-question [POST]
- /api/courseware-quiz/generate-subjects [POST]
- /api/courseware-quiz/generate-subjects-by-text [POST]
- /api/courseware-quiz/quiz/ [GET, POST, PUT]
- /api/courseware-quiz/settings [GET]

### curriculum-classifications

- /api/curriculum-classifications [GET]

### data-import

- /api/data-import/chaoxing-score/ [POST]
- /api/data-import/course-groups [POST]
- /api/data-import/course/ [POST]
- /api/data-import/courses [POST]
- /api/data-import/edit-courses [POST]
- /api/data-import/enrollments [POST]
- /api/data-import/enrollments/ [POST]
- /api/data-import/from-word [POST]
- /api/data-import/item_scores/ [POST]
- /api/data-import/scores/ [POST]
- /api/data-import/seat-number/ [POST]
- /api/data-import/validation [POST]

### departments

- /api/departments [unknown]
- /api/departments/ [GET]
- /api/departments? [GET]
- /api/departments?no-intercept=true [GET]

### ding-talk

- /api/ding-talk/chat?course_id= [GET, PUT]
- /api/ding-talk/user-id [GET]

### dingtalk-lives

- /api/dingtalk-lives/ [unknown]

### entries

- /api/entries [GET]

### exam

- /api/exam/ [GET]

### exams

- /api/exams/ [DELETE, POST]
- /api/exams/batch_delete [DELETE]

### grades

- /api/grades [unknown]
- /api/grades?org_id= [unknown]

### grant

- /api/grant/code/ [unknown]
- /api/grant/code?uid= [unknown]

### group-sets

- /api/group-sets/ [DELETE, GET, POST, PUT]

### groups

- /api/groups/ [DELETE, PUT]

### h5-courseware

- /api/h5-courseware/ [unknown]

### homework

- /api/homework/ [GET, PUT]

### instruction-team

- /api/instruction-team/meeting [GET]

### invites

- /api/invites/ [GET, POST]

### knowledge-capture-visit

- /api/knowledge-capture-visit [unknown]

### knowledge-graph

- /api/knowledge-graph/courses/ [GET, POST]
- /api/knowledge-graph/forest-versions/-/stats:batchGet [GET]
- /api/knowledge-graph/kfs-courses/-/published-forest-versions:batchGet [GET]
- /api/knowledge-graph/kfs-subjects [GET]

### knowledge-node

- /api/knowledge-node/ [DELETE, GET, POST, PUT]

### knowledge-nodes

- /api/knowledge-nodes/ [GET]
- /api/knowledge-nodes/parse/docx [POST]

### knowledge-resource-visit

- /api/knowledge-resource-visit [unknown]

### lark

- /api/lark/authorization/check [GET]
- /api/lark/files [GET]

### lecture-live

- /api/lecture-live/schedule/ [POST]
- /api/lecture-live?jwt= [unknown]

### lesson-resources

- /api/lesson-resources/shared-stat [GET]

### live-records

- /api/live-records/ [GET, POST]

### management

- /api/management/calendar-meeting/excel [POST]
- /api/management/calendar-meeting?page= [POST]

### meeting

- /api/meeting/ [unknown]

### modules

- /api/modules/ [PUT]

### my-academic-years

- /api/my-academic-years?fields=id [unknown]

### my-captures

- /api/my-captures [GET]

### my-courses

- /api/my-courses [POST]

### my-curriculum-academic-years

- /api/my-curriculum-academic-years?fields=id [unknown]

### my-curriculum-semesters

- /api/my-curriculum-semesters? [GET]

### my-semesters

- /api/my-semesters [GET]
- /api/my-semesters? [GET]

### my-semesters-all

- /api/my-semesters-all [unknown]

### ng.

- /api/ng. [unknown]

### ngSanitize

- /api/ngSanitize [unknown]

### notes

- /api/notes [POST]
- /api/notes/ [DELETE, PUT]
- /api/notes?course_id= [GET]

### obe

- /api/obe/existed-metrics?params= [unknown]

### online-videos

- /api/online-videos/ [GET]

### org

- /api/org [GET]
- /api/org/ [unknown]

### org-bulletin

- /api/org-bulletin/bulletins [GET, POST]
- /api/org-bulletin/bulletins/ [DELETE, POST, PUT]
- /api/org-bulletin/bulletins?fields=id [GET]
- /api/org-bulletin/classifications [GET]

### orgs

- /api/orgs/ [GET]

### outline

- /api/outline/notify [POST]

### program

- /api/program/course-programs?department_ids= [unknown]
- /api/program/user-programs?fields= [unknown]

### public-captures

- /api/public-captures [GET]

### public-resources

- /api/public-resources [unknown]

### questionnaires

- /api/questionnaires/ [GET]

### resource-file

- /api/resource-file/ [unknown]
- /api/resource-file/org/arrears/ [GET]

### resource-group

- /api/resource-group [POST]
- /api/resource-group/ [DELETE, PUT]

### resource-groups

- /api/resource-groups [GET]
- /api/resource-groups/ [DELETE, GET, POST, PUT]
- /api/resource-groups/folders [GET]
- /api/resource-groups/resources [GET]
- /api/resource-groups?page= [POST]

### resources

- /api/resources/ [GET]

### rollcall

- /api/rollcall/ [unknown]
- /api/rollcall/merged-rollcall [POST]
- /api/rollcall/merged-rollcall/student-rollcalls [PUT]

### semesters

- /api/semesters [unknown]

### shared-resource

- /api/shared-resource/classifications [unknown]

### shared-resources

- /api/shared-resources/ [DELETE]
- /api/shared-resources/management [GET]
- /api/shared-resources/stat [GET]
- /api/shared-resources/stat/video-resources [GET]
- /api/shared-resources/stat/video-resources/export [GET]

### slides

- /api/slides?keyword= [GET]

### stat

- /api/stat/activities-for-courses [GET]
- /api/stat/attendance/export/to/ [POST]
- /api/stat/courses/ [GET]
- /api/stat/courses/class-hours/export [GET]
- /api/stat/courses/export/to/ [POST]
- /api/stat/courses/homework-correct/export [GET]
- /api/stat/courses/rollcall/export [GET]
- /api/stat/courses/rollcall/export-by-class [GET]
- /api/stat/vtrses/ [GET]

### statistic

- /api/statistic [unknown]

### subject-libs

- /api/subject-libs/ [DELETE]

### submissions

- /api/submissions/ [GET, POST]

### syllabus

- /api/syllabus/ [PUT]

### tencent_meeting

- /api/tencent_meeting/check-user-auth [GET]

### toggle-opened-orgs

- /api/toggle-opened-orgs?toggle=org_team_teaching [GET]

### top-departments

- /api/top-departments?fields= [GET]

### uploads

- /api/uploads [POST]
- /api/uploads/ [DELETE, GET, POST, PUT]
- /api/uploads/audio/ [unknown]
- /api/uploads/batch/blob [POST]
- /api/uploads/details/query [POST]
- /api/uploads/document/ [GET]
- /api/uploads/embed-material/ [unknown]
- /api/uploads/marked_attachment/ [DELETE]
- /api/uploads/moodle-pkg?page= [GET]
- /api/uploads/reference/document/ [unknown]
- /api/uploads/references/ [PUT]
- /api/uploads/scorm/ [unknown]
- /api/uploads/screen-shot [POST]
- /api/uploads/screen-shot/share-to [POST]
- /api/uploads/share-to-courses [POST]

### uptoken

- /api/uptoken?id= [GET]

### user

- /api/user/academic-learning-resources [GET]
- /api/user/association-code [PUT]
- /api/user/chat [GET, POST]
- /api/user/check-expired-password [GET]
- /api/user/classes [unknown]
- /api/user/course-certification/scores [PUT]
- /api/user/course/ [GET]
- /api/user/language [PUT]
- /api/user/links [POST]
- /api/user/links/ [PUT]
- /api/user/other-video-resources [GET]
- /api/user/pre-task [GET]
- /api/user/recently-visited-courses [GET, PUT]
- /api/user/resources [GET]
- /api/user/search [GET]
- /api/user/send_org_sing_up_verification_email [unknown]
- /api/user/send_verification_email [unknown]
- /api/user/storage-used [GET]
- /api/user/third-part-resources [GET]
- /api/user?type=all&response_key= [unknown]
- /api/user?type=instructor [unknown]

### user-actions

- /api/user-actions?jwt= [unknown]

### user-visits

- /api/user-visits [unknown]

### users

- /api/users/ [GET]
- /api/users?page= [POST]

### video-quizzes

- /api/video-quizzes/ [GET]
- /api/video-quizzes/org/arrears/ [GET]

### virtual-classroom-resources

- /api/virtual-classroom-resources [GET, POST]

### vtrses

- /api/vtrses [GET]
- /api/vtrses/ [DELETE, GET, POST, PUT]
- /api/vtrses/resources/classifications/ [DELETE, GET, PUT]
- /api/vtrses/share-resources [GET]

### warning

- /api/warning/student/ [PUT]

### wedrive

- /api/wedrive/files?page= [unknown]

## 7. Recommended High-Level API Families

- Todos: /api/todos
- Courses: /api/my-courses, /api/course/, /api/courses, /api/user/recently-visited-courses
- Activities: /api/course/activities/, /api/activities/, /api/course/activities-read/
- Homework / Exams / Questionnaires: /api/homework/, /api/exams/, /api/questionnaires/
- Submissions: /api/submissions/
- Notes: /api/notes
- Grades: /api/grades
- Bulletins: /api/org-bulletin/bulletins, /api/org-bulletin/classifications
- Resource groups: /api/resource-groups, /api/resource-groups/folders, /api/resource-groups/resources
- Calendar: /api/calendar-events, /api/calendar-timetables

## 8. MCP Mapping

The local TronClass MCP server in this repository exposes high-level tools covering the families above, plus a raw_api tool for arbitrary /api access.
