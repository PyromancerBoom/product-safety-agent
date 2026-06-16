# ShopSafe Query Planner Playbook

## Rule: Prioritize Official Regulatory and Scientific Databases
- Trigger: Queries related to drug safety, medical devices, health claims, ingredient safety, or scientific evidence.
- Instruction: Always append `site:fda.gov OR site:nih.gov OR site:clinicaltrials.gov OR site:pubmed.ncbi.nlm.nih.gov` to queries. If the user context implies a specific regulatory body (e.g., European Medicines Agency), adjust the `site` operator accordingly.

## Rule: Avoid Generic Search Terms for Evidence
- Trigger: Queries where the user is asking for evidence or scientific backing for a health claim, side effect, or drug interaction.
- Instruction: Replace vague terms like "is it safe" or "does it work" with more specific scientific or regulatory language. For example, instead of "Is Ingredient X safe for children?", search for "Ingredient X safety profile children FDA" or "Ingredient X adverse effects pediatric clinical trials".

## Rule: Maintain User Context for Specific Populations and Conditions
- Trigger: User queries that mention specific demographics (pregnant, children, elderly), medical conditions (diabetes, heart disease), or allergies.
- Instruction: Explicitly include these keywords in the search query. For example, if the user asks about a medication while pregnant, search for "[Medication Name] pregnancy safety FDA" or "[Medication Name] contraindications pregnancy NIH". For allergies, search for "[Allergen] cross-reactivity [Substance] toxicology".

## Rule: Neutral and Objective Query Phrasing
- Trigger: Queries that use alarmist, leading, or biased language (e.g., "X causes cancer", "Big Pharma hides the truth about Y").
- Instruction: Rephrase the query to be neutral and objective. Instead of "Does [Product] cause cancer?", search for "[Product] carcinogenicity studies NIH" or "[Product] FDA adverse event reporting cancer". Focus on factual reporting of studies and official assessments.

## Rule: Target Specific Ingredient or Compound Information
- Trigger: Queries about the safety or efficacy of a specific chemical compound, ingredient, or drug.
- Instruction: Use precise scientific or chemical names. When searching for information on active ingredients in cosmetics or supplements, prioritize databases like FDA's VCRP (Voluntary Cosmetic Registration Program) if applicable, or general safety databases like PubChem and TOXNET (through NIH). Append `site:fda.gov OR site:nih.gov` for regulatory and scientific data.