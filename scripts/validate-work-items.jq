(if length == 1 then .[0] else error("Expected one implementation matrix") end) |
if type == "array" and length <= (if $event == "push" then 256 else 1 end) and
  all(.[];
    type == "object" and
    (keys == ["issue_number", "reply_number", "source_pr", "tracking_label"]) and
    (.issue_number | type == "string" and test("\\A[1-9][0-9]*\\z")) and
    (.source_pr | type == "string" and test("\\A([1-9][0-9]*)?\\z")) and
    ($event != "push" or .source_pr != "") and
    (.reply_number | type == "string" and test("\\A[1-9][0-9]*\\z")) and
    .tracking_label == ("factory-issue-" + .issue_number) and
    .reply_number == (if .source_pr == "" then .issue_number else .source_pr end)
  ) and
  ([.[].tracking_label] | length == (unique | length)) and
  ([.[].reply_number] | length == (unique | length))
then . else error("Invalid or oversized implementation matrix") end
