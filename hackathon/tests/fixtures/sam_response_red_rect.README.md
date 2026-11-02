# Fixture: sam_response_red_rect.json

Live SAM 3.1 response captured 2026-10-26 (operator receipt, first credit spend).
Input: /tmp test poster 640x400, prompt "red rectangle", data-URI PNG, POST
https://api.meta.ai/v1/responses, stream=false, HTTP 200.

Response shape (parse contract for h3 decoder):
- output[0].content[0].text = special-token stream:
  "<0f>0" prefix, then "<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|>" per match,
  then "<|mask;x=..;y=..;data=<rle-ish string>|>" per match.
- Box coordinates are PIXEL-EXACT vs the drawn rectangle [60,260,220,330].
- Full response JSON is committed verbatim as the fixture.
