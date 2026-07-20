import assert from "node:assert/strict";
import test from "node:test";

import { markSafetyAcknowledged } from "../src/messageState.js";


test("safety acknowledgement persists on the App-owned message", () => {
  const messages = [
    { id: "welcome", role: "assistant", text: "Hello" },
    {
      kind: "proactive",
      message_id: "pm-safety",
      trigger_type: "safety",
      related_id: "alert-1",
      text: "Are you okay?",
    },
  ];

  const updated = markSafetyAcknowledged(messages, "pm-safety");

  assert.notStrictEqual(updated, messages);
  assert.equal(messages[1].safety_acknowledged, undefined);
  assert.equal(updated[1].safety_acknowledged, true);
  assert.strictEqual(
    updated.find((message) => message.message_id === "pm-safety"),
    updated[1],
  );
});


test("repeated or unknown acknowledgements preserve the message array", () => {
  const messages = [
    { message_id: "pm-safety", safety_acknowledged: true },
  ];

  assert.strictEqual(markSafetyAcknowledged(messages, "pm-safety"), messages);
  assert.strictEqual(markSafetyAcknowledged(messages, "missing"), messages);
});
