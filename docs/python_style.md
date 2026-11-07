# Versuz — Python API Style

How backend code reads. Josh's rules, his words where he gave them.
Test: a junior dev walks through it at a glance. Clarity is king, even at the cost of speed.

Part 1 is the rules. Part 2 is the A/B test (2026-10-12) the rules came from.

---

## Part 1 — The rules

### Shape of a function

- One step per line. Blank line between steps.
- Name first, then use. Every request field and every query gets its own named line before the call.
- Early return. Leave as soon as the answer is known.
- Constants: every UPPER_CASE value in one block after the imports. Banners hold functions only.
- A section opens with its build function (four or five lines, one per part). Each part's function sits below, then what it calls, in call order.

### Comments

| Where | Rule |
|---|---|
| `views.py` | Five words or less above each line that does something. One per call inside a query chain too. |
| Everything else (models, helpers, games, admin) | A full sentence above each step, plain words. |
| Anywhere | Never trailing. No comment that restates an obvious line. Model fields get none. |

### Use / not

| Use | Not |
|---|---|
| for-i loops, `if`, `len`, `append`, indexing | comprehensions of any shape, generators |
| named variables: `selected_game`, `num_verses` | `_`, `lambda`, decorators, `itertools`, `next()`, `zip` tricks, `enumerate` unpacking |
| `split()` | `.find()` plus slice math |
| modulo, with a comment saying what it does | nested calls on one line |
| a temp variable to swap two things | one-line tuple swap |
| dict literal on one line when it fits | |
| one `create()` per row, one builder per round | `bulk_create`, caches for a handful of rows |

Lists are built with a loop and `append`, even when a comprehension fits on one line.

### Shapes

Query chain — parentheses, one call per line, short comment above each:

```python
notifications = (
    Notification.objects
    # That have started
    .filter(start__lte=now)
    # But not ended
    .filter(Q(end__isnull=True) | Q(end__gt=now))
    # Not dismissed by this player
    .exclude(dismissals__user=request.user)
)
```

404:

```python
verse = MemoryVerse.objects.filter(id=verse_id, user=request.user).first()
if verse is None:
    return Response(status=404)
```

Read, validate, name, write, reply:

```python
errors = MemoryVerse.validate(request.data)
if errors:
    return Response(errors, status=400)

book_id = request.data['book_id']
chapter = request.data['chapter']

verse = MemoryVerse.objects.create(
    user=request.user,
    book_id=book_id,
    chapter=chapter,
)
return Response(verse.to_dict(), status=201)
```

Update is the same shape — one call, one keyword per line:

```python
MemoryVerse.objects.filter(id=verse.id).update(
    book_id=book_id,
    chapter=chapter,
)
verse.refresh_from_db()
```

Validate — types first, then logic, first error returns:

```python
@staticmethod
def validate(data):
    if not is_int(data['chapter']):
        return ['Chapter must be a number.']

    if data['chapter'] < 1:
        return ['Chapter must be 1 or more.']

    return []
```

### Names

- Everyday words. Verb first for functions: `pick_blanks`, `calculate_num_blanks`, `build_word_bank`.
- Say the full thing: word bank, not bank. No question-shaped names (`how_many_blanks`).
- One noun per thing. Words, not tokens / pieces / chips / marks. `split_into_words`, not tokenize. `make_plain`, not normalize.
- Before adding a noun, check whether a word already in the file covers it.
- Names say what they hold: `book_exists`, `verse_deck`, `practice_day`.
- Loop item keeps the plain name (`name`); the cleaned copy is `cleaned_name`. Never `raw_`.
- Contract keys the game reads stay as they are.

### Payloads and errors

- Read with `request.data['field']`. Never `.get()`, never a default. A missing field crashes, as it should.
- Validation is never in a view. Views stay light: read, validate, write, reply.
- `Model.validate(data)` is a `@staticmethod` on the model. Types first (`is_int`), then logic. Returns at the first error: a list with one message, in player words.
- Only player-typed values get checked. Values the game makes (ids, swing results, clocks) are trusted.
- No `(errors, cleaned)` pairs, no `.pop()`, no `or []` guards.
- Writes are one call, one line per parameter. Never `**`.

### Where things live

- `models/<name>.py`: one model per file. `__init__.py` holds imports only.
- Checks about one model: `@staticmethod` on it. Writes about its relations: methods (`verse.set_tags`).
- `helpers/<topic>.py`: small pure functions (`is_int`). Input in, result out, no orchestration.
- `views.py`: views only. Every view inherits `AuthView` or `NoAuthView`. The class name is the security doc.
- No DRF serializers. Each model has `to_dict()`, explicit fields only.
- The function that needs a DB list fetches it itself. No injecting through `__init__`, arguments or a parent's cache.

### Trust

- Backend trusts the game, game trusts the backend. No cross-checks, no re-validation.
- A function never cleans up another function's output. Fix the producer.
- No `list()`, copies or guards "just in case". A wrapper that is truly needed says why in the comment above it.
- Drop special cases the real data never has.
- The game is the only client. Timing fields are dead. `elapsed_seconds` stays for stats.
- The server builds all game material. The game renders it.

### Josh's draft code

- A `jg_` view or function defines what it names. Use it as written. No simpler stand-in.
- `JoshTestView` / `GrantTestView` are scratch space. Not graded, not cut, not in the contract.

### Grading

Before done: read each function aloud as English. Every line passes Use / not, every name passes Names, every request line passes Payloads and errors. A new style call from Josh goes in this file in the same task.

---

## Part 2 — The A/B test (2026-10-12)

Deck: "views.py Style A/B". Every view and helper once, A and B differing on one thing. Josh picked and wrote why.

### Picks

| # | Spot | Question | Pick | Josh's words | Rule it became |
|---|---|---|---|---|---|
| 02 | BibleBooksView | three-line comprehension vs loop | **B** loop | | Loops only. Comprehension exception gone. |
| 03 | GamesView | query inline vs named first | **B** named | | Name first, then use. |
| 04 | NotificationsView | one chain vs one filter per step | **A** chain | "5 word or less english descriptions of what each line is doing… Notifications, That have started, But not ended, Have not been dismissed" | Chain in parentheses, short comment per call. Five-word comments in views. |
| 05 | NotificationDismissView | filter + first + if vs `get_object_or_404` | **A** filter | | 404 = filter, first, if None. |
| 06 | SettingsView | `to_dict` + profile vs reply spelled out | **B** spelled out | "These comments seem not clear" | See every key of the reply in the view. |
| 07 | VersesView.get | chained vs two statements | **A** chained | | Chain shape confirmed. |
| 08 | VersesView.post | `request.data` at the call vs each field named first | **B** named | | Every request field on its own line before use. |
| 10 | PracticeSessionsView checks | checks in view vs on model | **B** model | "never validation in a view - views should be light" | `Model.validate` on every POST. |
| 11 | PracticeSessionsView rows | create per round vs `bulk_create` | **A** per round | "clarity at cost of speed" | One create per row. |
| 12 | PracticeSessionsView material | builder per round vs dict of builders | **A** per round | "clarity is king" | No caches for a handful of rows. |
| 13 | PSGameSwingsView | early return vs one return | **A** early | | Early return. |
| 14 | CompleteView counting | one loop with guard vs two loops | **A** one loop | "confusing through" | Keep one pass. |
| 19 | MemoryVerse.validate | keep `is_int` vs trust ints | **A** keep | "is_int is good validation - just validate types THEN validate logic, use an early return of the first error, they don't need to know all their errors at once." | Types, then logic, first error returns. |
| 20 | MemoryVerse.set_tags | reuse loop name vs new name | **B** new name | "raw_name >> name, name >> cleaned_name…. don't use raw but do use 'cleaned'" | `name` / `cleaned_name`. Never `raw_`. |

### Skipped, with notes

| # | Spot | Josh's words | Outcome |
|---|---|---|---|
| 01 | JGTestView | "Too long of a code snippet" | Scratch space, not graded. |
| 09 | VerseDetailView.patch (verse_end rule) | "Too long" | Same shape as POST: name first, one update call. |
| 15 | CompleteView stamping | "Now I'm asking the question of what views can I cut, what data can I cut out - where is this stuff over engineered!!!" | Led to the Backend Cut List deck, same day. |
| 16 | CompleteView recap sort key | "What is this used for? Again is it over engineering, something to nuke?" | On the cut list. |
| 17 | deal_balanced_deck | "What is this used for? Again is it over engineering, something to nuke?" | "Don't touch dealing for now." `helpers/deck.py` stays as is. |
| 18 | break_up_repeats | "Neither looks that human readable…" | Same. Dealing untouched. |

### Same day, after the picks

- "5 words rule is for the views." Models, helpers, games, admin keep full-sentence comments.
- "Don't touch dealing for now."
- Cut list: views and tables only, grouped by the part of the phone they touch. Dead functions on their own slide.

### Earlier calls that fed the deck

| Date | Call |
|---|---|
| 2026-09-25 | "I prefer simple code concepts over advanced python." Comprehension + modulo and `itertools.cycle` + `next()` + `_` both rejected. His own for-i loop was the standard. |
| 2026-09-25 | "All constants should be at the top of files." |
| 2026-09-25 | "Normalize sounds like a helper not a manager." Helpers vs managers by the sound of the name. |
| 2026-09-25 | "Only have what needs filler words make the query." No constructor injection. |
| 2026-09-27 | "Tokenize and tokens isn't hitting home for me." Everyday words, verb first. |
| 2026-10-03 | "Isn't this cleaning up a mess that the tokenizer creates??? It isn't the responsibility of one function to clean up another's!" |
| 2026-10-03 | "Don't do defensive coding like this!!" on `list(...)` around a queryset. |
| 2026-10-03 | "'chips' isn't a good word - I don't like that mental model." |
| 2026-10-04 | "I REALLY don't like this one" on `.find()` + slice math. `split()` instead. |
| 2026-10-04 | "I don't like the word pieces - it is breaking my mental model." One noun: words. |
| 2026-10-05 | "I hate .get() and defensive coding - make stuff break loudly." |
| 2026-10-05 | "Just have validation return a list of errors - if errors, return 400." |
| 2026-10-05 | "Don't use ** for creating objects….. spell out each parameter, one parameter per line." |
| 2026-10-05 | "You can still use one function call just use one line per param" on PATCH. |
| 2026-10-05 | "Think bigger than just this one spot though - this is a coding style shift." |
| 2026-10-17 | "Loud no-reason comments" rejected. Model fields bare. |
