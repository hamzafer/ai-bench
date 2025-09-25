#!/usr/bin/env bash

# Simple curl invocation against the comment analysis endpoint without auth headers
curl "https://hero.deepinsight.internal/api/comment-analysis/analyze" \
  -H 'Content-Type: application/json' \
  --data '{"comment_text":"Kan komme på kort varsel dersom vi får en avlysning. Bor i nærheten."}'
