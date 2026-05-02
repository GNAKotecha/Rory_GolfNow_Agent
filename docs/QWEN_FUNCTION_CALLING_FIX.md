# qwen2.5-coder Function Calling Fix

## Problem

qwen2.5-coder models return tool calls inconsistently:
- Sometimes: Properly parsed as structured `tool_calls` (multi-step workflow)
- Sometimes: JSON returned as plain text in `content` field (single-step workflow)

This causes unpredictable agentic behavior on production RunPod deployment.

## Root Cause

**Template Mismatch** ([Source: GitHub Issue #180](https://github.com/QwenLM/Qwen3-Coder/issues/180))

1. **qwen2.5-coder** was trained with **Qwen2-style** function calling:
   - Uses `<tool_call>...</tool_call>` XML-style tags
   - Model outputs tool calls in this format

2. **Ollama's default template parser** expects:
   - `[tool_call]...[/tool_call]` bracket-style tags (hermes format)
   - When template says `<tool_call>`, Ollama doesn't recognize tool calls as structured data

3. **Result**:
   - Model returns: `<tool_call>{"name":"calculate","arguments":{...}}</tool_call>`
   - Ollama sees: Plain text content (not structured tool_calls)
   - Our workaround: Parse JSON from text with `content.find("{")`

## Proper Solution

Fix the Ollama model template to use correct bracket format:

### Step 1: Run Fix Script

```bash
# On Ollama host (RunPod VM)
bash /tmp/fix_qwen_template.sh
```

This will:
1. Extract current Modelfile: `ollama show qwen2.5-coder:32b --modelfile`
2. Replace `<tool_call>` → `[tool_call]` in TEMPLATE section
3. Replace `</tool_call>` → `[/tool_call]`
4. Create fixed model: `qwen2.5-coder-fixed:32b`

### Step 2: Update Backend Configuration

**File**: `backend/app/services/ollama.py:21`

```python
# Change from:
self.default_model = "qwen2.5-coder:32b"

# To:
self.default_model = "qwen2.5-coder-fixed:32b"
```

### Step 3: Remove JSON Parsing Workaround (Optional)

**File**: `backend/app/services/ollama.py:192-239`

The JSON detection logic can be simplified or removed once template is fixed, since Ollama will properly return structured `tool_calls` instead of text content.

## Expected Behavior After Fix

### Before (Inconsistent)
- Request 1: `{"type": "text", "content": '{"name":"calculate",...}'}`
- Request 2: `{"type": "tool_calls", "tool_calls": [...]}`

### After (Consistent)
- All requests: `{"type": "tool_calls", "tool_calls": [...]}`

## Testing

```bash
# Test tool calling endpoint
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer <token>" \
  -d '{
    "session_id": 1,
    "message": "Calculate 25 * 4, store as product"
  }'

# Should consistently show:
# - workflow_complete at step 2+ (not step 1)
# - tool_calls event in stream
# - structured tool execution logs
```

## Technical Details

### Why This Works

Ollama uses Go template parsing ([source](https://github.com/ollama/ollama/blob/66fb8575ced090a969c9529c88ee57a8df1259c2/tools/template.go#L13)):

```go
// Ollama expects this format for tool detection:
toolCallPattern = `\[tool_call\](.*?)\[/tool_call\]`

// With <tool_call> tags, pattern doesn't match
// With [tool_call] tags, pattern matches and parses as structured data
```

### Why qwen2.5-coder Uses Different Format

From GitHub discussion:
- **Qwen2.5 base models** (7B-Instruct, 32B-Instruct): Trained with hermes-style `[tool_call]` → Works with vLLM/Ollama
- **Qwen2.5-coder models**: Trained with Qwen2-style `<tool_call>` → Requires template fix for Ollama

This explains why:
- Normal Qwen2.5 models work perfectly with function calling out of the box
- Coder models need template customization

## Alternative Solutions (Not Recommended)

1. **Use Qwen2.5-32B-Instruct instead**: Works without fix, but loses code specialization
2. **Keep JSON parsing workaround**: Works but less reliable, doesn't fix root cause
3. **Use vLLM with custom parser**: More complex infrastructure change

## References

- [GitHub Issue #180](https://github.com/QwenLM/Qwen3-Coder/issues/180) - Original bug report and solution discovery
- [Comment #14 by WinPooh32](https://github.com/QwenLM/Qwen3-Coder/issues/180#issuecomment-2569959697) - Template fix trick
- [Comment #16 by Gabrielsv01](https://github.com/QwenLM/Qwen3-Coder/issues/180#issuecomment-2601877439) - Complete working solution
- [Ollama template.go](https://github.com/ollama/ollama/blob/66fb8575ced090a969c9529c88ee57a8df1259c2/tools/template.go#L13) - Tool call pattern matching code
- [Qwen2 Function Calling Docs](https://qwen.readthedocs.io/en/latest/framework/function_call.html#qwen2-function-calling-template) - Qwen2-style format
- [Qwen2.5 Function Calling Docs](https://qwen.readthedocs.io/en/latest/framework/function_call.html#qwen2-5-function-calling-templates) - Hermes-style format

## Next Steps

1. ✅ Create fix script: `/tmp/fix_qwen_template.sh`
2. ⏳ Run script on RunPod Ollama VM
3. ⏳ Update `ollama.py` default model name
4. ⏳ Test on production deployment
5. ⏳ (Optional) Remove JSON parsing workaround if confident in fix
6. ⏳ Document fix in CLAUDE.md
