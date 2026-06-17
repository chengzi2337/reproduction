# IFBench GEPA final prompt surgery 预检报告

## 结论

- program：`C:\Users\lin\Documents\New project 2\.codex\gepa-artifact\experiment_runs_data\experiment_runs\seed_0\IFBench_IFBenchCoT2StageProgram_GEPA_qwen3-8b-dashscope-paper-adapted\evaluation_results\optimized_program`
- 写变体门禁：`needs_safe_dspy_load_before_writing_variants`
- 原因：当前工具只做离线审计和手术方案预检；不能直接二进制修改 pickle。写出 P1/P2/P3 必须先通过 dspy.load 稳定加载 program，再只修改 predictor signature instruction/docstring 并重新保存。

## 偏置命中

### long_answer

- pattern：`at least\s+3\s+sentences`，offset：`745`

```text
69919a07996a9a1523.Nt.R.h..._class_setstate...h%}.(..__abstractmethods__.(....__annotations__.}.(..query...builtins...str....	reasoning.h0..response.h0u..__class_vars__.....__doc__.Xl...Respond to the query by providing a clear and concise explanation. Your response must contain at least 3 sentences. If the query includes specific formatting or content requirements (such as limiting the use of all-caps words, requiring a certain number of sentences, or including placeholders like [address]), ensure those are strictly followed. Additionally, if the query
```

- pattern：`clear and concise explanation`，offset：`687`

```text
ature.h..	Signature.....}..
__module__.h.s. 12d11fd80a124169919a07996a9a1523.Nt.R.h..._class_setstate...h%}.(..__abstractmethods__.(....__annotations__.}.(..query...builtins...str....	reasoning.h0..response.h0u..__class_vars__.....__doc__.Xl...Respond to the query by providing a clear and concise explanation. Your response must contain at least 3 sentences. If the query includes specific formatting or content requirements (such as limiting the use of all-caps words, requiring a certain number of sentences, or including placeholders like [address]), ensur
```

- pattern：`well-structured language`，offset：`9131`

```text
n syntax) exactly as specified.
3. **Ensure the content is accurate, ethical, and factually correct**, especially when dealing with sensitive topics such as health, science, or public policy. Avoid promoting false, harmful, or misleading information.
4. **Use clear, concise, and well-structured language** to convey your response. If the task involves coding or technical implementation, ensure that the code is syntactically correct and logically sound.
5. **Include appropriate error handling and data validation** when relevant, especially for tasks involv
```

- pattern：`multi-part tasks`，offset：`11421`

```text
context-aware responses that avoid bias, promote fairness, and align with widely accepted ethical standards.
- **For coding tasks**, ensure that the code is properly indented, uses meaningful variable names, and includes comments where necessary to explain complex logic.
- **For multi-part tasks**, break down the response into distinct sections, each addressing a specific part of the query, and label them clearly for readability.

By following these detailed instructions, you will ensure that your responses are not only compliant with the userâ..s specif
```
### structured

- pattern：`structured`，offset：`9136`

```text
tax) exactly as specified.
3. **Ensure the content is accurate, ethical, and factually correct**, especially when dealing with sensitive topics such as health, science, or public policy. Avoid promoting false, harmful, or misleading information.
4. **Use clear, concise, and well-structured language** to convey your response. If the task involves coding or technical implementation, ensure that the code is syntactically correct and logically sound.
5. **Include appropriate error handling and data validation** when relevant, especially for tasks involving u
```

- pattern：`sections`，offset：`11479`

```text
 and align with widely accepted ethical standards.
- **For coding tasks**, ensure that the code is properly indented, uses meaningful variable names, and includes comments where necessary to explain complex logic.
- **For multi-part tasks**, break down the response into distinct sections, each addressing a specific part of the query, and label them clearly for readability.

By following these detailed instructions, you will ensure that your responses are not only compliant with the userâ..s specifications but also aligned with best practices in accuracy,
```

- pattern：`breakdown`，offset：`10593`

```text
 ensure that the final response contains the `reasoning`, `final_response`, and `completed` markers, and that the content is both ethically sound and technically correct.

Additionally:
- **For mathematical or logical problems**, ensure that your solution includes a step-by-step breakdown of the reasoning process, using proper arithmetic and logical operators.
- **For database design tasks**, use SQL syntax and schema definitions that are compatible with PostgreSQL or similar relational databases. Include primary keys, foreign keys, and appropriate data
```
### step_by_step

- pattern：`step-by-step`，offset：`10580`

```text
ns.

Finally, ensure that the final response contains the `reasoning`, `final_response`, and `completed` markers, and that the content is both ethically sound and technically correct.

Additionally:
- **For mathematical or logical problems**, ensure that your solution includes a step-by-step breakdown of the reasoning process, using proper arithmetic and logical operators.
- **For database design tasks**, use SQL syntax and schema definitions that are compatible with PostgreSQL or similar relational databases. Include primary keys, foreign keys, and appr
```

- pattern：`reasoning process`，offset：`10610`

```text
final response contains the `reasoning`, `final_response`, and `completed` markers, and that the content is both ethically sound and technically correct.

Additionally:
- **For mathematical or logical problems**, ensure that your solution includes a step-by-step breakdown of the reasoning process, using proper arithmetic and logical operators.
- **For database design tasks**, use SQL syntax and schema definitions that are compatible with PostgreSQL or similar relational databases. Include primary keys, foreign keys, and appropriate data types.
- **For te
```

- pattern：`breakdown of the reasoning`，offset：`10593`

```text
 ensure that the final response contains the `reasoning`, `final_response`, and `completed` markers, and that the content is both ethically sound and technically correct.

Additionally:
- **For mathematical or logical problems**, ensure that your solution includes a step-by-step breakdown of the reasoning process, using proper arithmetic and logical operators.
- **For database design tasks**, use SQL syntax and schema definitions that are compatible with PostgreSQL or similar relational databases. Include primary keys, foreign keys, and appropriate data
```
### safety_or_ethics

- pattern：`ethically sound`，offset：`10443`

```text
ollowed precisely. Adhere to all constraints, even if they seem trivial, to ensure the response is usable and meets the user's expectations.

Finally, ensure that the final response contains the `reasoning`, `final_response`, and `completed` markers, and that the content is both ethically sound and technically correct.

Additionally:
- **For mathematical or logical problems**, ensure that your solution includes a step-by-step breakdown of the reasoning process, using proper arithmetic and logical operators.
- **For database design tasks**, use SQL syntax
```

- pattern：`sensitive topics`，offset：`8983`

```text
matting or constraints mentioned in the query.
2. **Follow all formatting instructions** provided in the query (e.g., bullet points, titles, markdown syntax) exactly as specified.
3. **Ensure the content is accurate, ethical, and factually correct**, especially when dealing with sensitive topics such as health, science, or public policy. Avoid promoting false, harmful, or misleading information.
4. **Use clear, concise, and well-structured language** to convey your response. If the task involves coding or technical implementation, ensure that the code is
```

- pattern：`unethical`，offset：`9470`

```text
task involves coding or technical implementation, ensure that the code is syntactically correct and logically sound.
5. **Include appropriate error handling and data validation** when relevant, especially for tasks involving user input or API interactions.
6. **If the request is unethical, harmful, or violates scientific consensus**, clearly state that you cannot fulfill the request while providing accurate, evidence-based information to guide the user toward reliable sources.

Incorporate domain-specific knowledge where applicable, such as understanding
```

- pattern：`harmful`，offset：`9066`

```text
ons** provided in the query (e.g., bullet points, titles, markdown syntax) exactly as specified.
3. **Ensure the content is accurate, ethical, and factually correct**, especially when dealing with sensitive topics such as health, science, or public policy. Avoid promoting false, harmful, or misleading information.
4. **Use clear, concise, and well-structured language** to convey your response. If the task involves coding or technical implementation, ensure that the code is syntactically correct and logically sound.
5. **Include appropriate error handling
```

## 手术变体

- `P0`：原 GEPA program。不修改 optimized program，只作为 replay 对照。
- `P1`：移除长回答/结构化/step-by-step/至少三句倾向。删除或弱化通用解释、至少三句、结构化标题和 step-by-step 倾向。
- `P2`：加入 hard-constraint priority。增加硬约束优先：字面格式、计数、分隔符、换行、长度和禁用词优先于解释性质量。
- `P3`：P1 + P2。同时移除通用长回答偏置，并加入 hard-constraint priority。
