# Planning System for DENNIS

## Overview
The planning system lets DENNIS build a full execution plan up front, then execute that plan sequentially without repeatedly calling the LLM after each tool call.

## Components
- Planner: converts a user request into a structured Plan.
- PlanExecutor: executes the steps sequentially.
- PlanReflector: converts execution results into a final response.
- Models: define Plan, PlanStep, ToolResult, ExecutionResult, ReflectionResult.

## Execution flow
1. User request enters Dennis.
2. The planner receives the request, available tools, memory summary, and context.
3. The planner returns a structured JSON plan with multiple steps.
4. The executor runs the plan sequentially.
5. Reflection turns execution results into a human-readable answer.

## Example plan
```json
{
  "goal": "Create a Python file in VS Code",
  "steps": [
    {"tool": "launch_app", "args": {"app_name_or_path": "Code"}, "retries": 1},
    {"tool": "focus_window", "args": {"title": "Visual Studio Code"}, "retries": 1},
    {"tool": "type_text", "args": {"text": "print('Hello World')"}, "retries": 1}
  ]
}
```

## Compatibility
The old prompt-based tool calling remains as a fallback, so the project remains backward compatible.
