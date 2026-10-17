# Scoring rubric

Score every dimension 1 to 5 against these anchors. Every score needs a one or two sentence rationale and at least one verbatim quote from the application. `render_report.py` checks each quote against the application text; a 4 or 5 with no quote it can find counts as a 3.

Score what the application shows, not what it implies. A skill in a skills list is a claim. The same skill inside a dated role, with a result attached, is evidence.

## Why these dimensions and weights

- **Structured, job-related criteria beat gut feel.** The 2022 Sackett et al. re-analysis of selection research put structured interviews at the top, with job knowledge and work-sample evidence close behind, and found older validity figures (including for unstructured judgment) were overstated. A resume screen is the weakest stage of that pipeline, so its job is to decide who gets a structured interview, using consistent anchors, and to hand the interviewer the right questions.
- **Personality from paper is weak.** Recruiter inferences of personality from resumes have low reliability and mostly lack validity (Journal of Business and Psychology, 244 recruiters). A 2024 study found some real resume cues for conscientiousness and openness, but they explain under a quarter of the trait. So work style carries a small weight, defaults to low confidence, and exists mainly to generate interview probes.
- **Learning agility gets real weight** because the hire will spend most of the first year on things the posting did not list. It is scored from behavior over time (what they picked up, how fast, what they did with it), not from adjectives.

Default weights (override in `requirements.json`):

| Dimension | Weight | What it answers |
|---|---|---|
| must_have | 30 | Can they do the non-negotiables today? |
| experience | 25 | Have they done comparable work at comparable scope, recently? |
| impact | 15 | Did their work change outcomes, in ways someone could check? |
| learning_agility | 15 | Will they get good at what they do not know yet? |
| work_style | 5 | Ownership, collaboration, communication. Low confidence by design. |
| nice_to_have | 10 | Preferred skills and domain extras. |

## Anchors

### must_have (Must-have skills)
- **5** Every must-have is demonstrated inside a dated role, most within the last 3 years, with scope or results attached.
- **4** Every must-have demonstrated; one is older than 3 years or thin on detail.
- **3** All must-haves present, but one or two only listed or only implied by an adjacent tool.
- **2** One must-have missing, or several only listed.
- **1** Two or more must-haves missing.

Use the scanner's coverage (demonstrated, listed, absent) as a starting point, then correct it. Adjacent tools count as partial, never met (GCP for AWS, Jenkins for GitHub Actions), and say so in the requirement call.

### experience (Relevant experience)
- **5** Same kind of work at the same or larger scope and level, recently, for long enough to have seen consequences (roughly 2+ years in at least one comparable role).
- **4** Comparable work at somewhat smaller scope, or one level below with a clear upward trend.
- **3** Adjacent work (related function or domain) that would transfer with ramp-up.
- **2** Some overlap, mostly a different job.
- **1** Little relevant experience.

Judge level by scope (team size, systems owned, budget, customers), not title. Do not reward years for their own sake; 15 years of the same year is not 15 years of growth.

### impact (Demonstrated impact)
- **5** Several specific, checkable outcomes tied to their own actions (numbers with a baseline, named systems, named customers or programs).
- **4** A few clear outcomes, some quantified.
- **3** Mostly duties, a couple of real results.
- **2** Duties only, or results so vague they cannot be checked ("drove alignment", "improved efficiency").
- **1** No outcomes at all.

The scanner's quantified-bullet ratio is a hint, not the score. A number with no baseline ("improved performance 300%") is weaker than a plain specific outcome ("cut nightly batch from 6 hours to 40 minutes").

### learning_agility (Learning agility)
Look for behavior over time:
- New tools, languages, or domains adopted and then used for real work (not just certifications).
- Stretch moves: function changes, domain changes, first-time lead or owner roles, and how quickly responsibility followed.
- Self-directed learning that produced something: side projects, open source, writing, teaching others, internal tools.
- Recency: are they still learning now, or did growth stop several years ago?
- Fast ramps: promoted or given new scope within about 12 to 18 months of joining or switching.

Anchors:
- **5** Two or more clear instances of learning something new and applying it to deliver results, including at least one recent one.
- **4** One strong instance plus steady skill growth across roles.
- **3** Normal growth inside one lane; skills current.
- **2** Static skill set, nothing new in several years.
- **1** Skills clearly dated for the role, no sign of recent learning.

Confidence is medium at best from paper. Always write at least one interview question for this dimension (see below).

### work_style (Work-style signals)
Paper evidence only, so default confidence is **low**. What counts:
- Ownership language tied to outcomes ("owned the on-call rotation and cut pages 40%"), not trait adjectives ("self-starter").
- Collaboration that names who and what (partnered with Finance on X, mentored 3 engineers who were promoted).
- Communication quality of the application itself: clear, specific, organized. Do not penalize non-native English phrasing or formatting choices.
- Follow-through: long projects completed, things maintained after launch.

Anchors: **5** several concrete instances across roles; **3** some, or only generic claims; **1** nothing beyond adjectives. Never infer temperament, culture fit, or personality type. Never score tone, humility, confidence, or likability.

### nice_to_have
- **5** Most preferred items demonstrated. **3** A few, or listed only. **1** None.

## Requirement calls

For each requirement in `requirements.json`, set `met`, `partial`, or `not_met` when you disagree with the scanner or want to confirm it. Leave it out to accept the scanner (demonstrated = met, listed = partial, absent = not_met). The scanner only sees words; correct it for synonyms, adjacent tools, and claims that are listed but contradicted by the timeline.

## Interview questions

Write 4 to 6 per candidate:
- 1 or 2 on the biggest gap or the weakest must-have.
- 1 on learning agility. Use the past-behavior format: "Tell me about the last time you had to get productive in a tool or domain you had never used. What did you do in the first two weeks? What would you do differently?" Tailor it to something on their resume.
- 1 on work style, behavioral ("Tell me about a time you disagreed with a technical decision your lead made").
- 1 to verify their strongest claim in depth (ask for the specifics a real owner would know: numbers, tradeoffs, what broke).
- 1 per integrity flag at Verify or above, phrased neutrally.

## What never goes into a score

Name, photo, age or graduation year, gender, race, ethnicity, national origin, citizenship (unless the role legally requires it), religion, disability, pregnancy, family status, veteran status as a negative, school prestige, accent, home location beyond the posting's stated location requirement, non-US education, and employment gaps. If a dimension cannot be scored without one of these, score what remains and say so.
