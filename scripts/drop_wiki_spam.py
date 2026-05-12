#!/usr/bin/env python3
"""Delete confirmed MediaWiki link-farm spam pages from the page corpus.

Two source wikis were vandalised by spammers in the unmoderated 2014-15 era:
  - ITfC_Course_Re-wiring_womens_rights/index.php/...  (30 spam pages)
  - ITfC_Annual_Report_2013-14/index.php/Good_Vices_That_Benefit_Our_Health

The legit pages on the same wikis (course faculty, session speakers, course
structure, About_Us, the 2012-13/2013-14/2014-15 annual reports, etc.) stay.

This module also exports `SPAM_SLUGS` for use as a denylist by
`refetch_latest.py` so the wiki spam can never re-enter the corpus via a
future Wayback fetch.

Idempotent. Pass --apply to write.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys

SHARDS = 'src/data/pages/*.json'

# Exact set of slugs to drop. Determined by manual content audit.
SPAM_SLUGS = {
    # 30 link-farm spam pages from the course wiki
    "ITfC_Course_Re-wiring_womens_rights/index.php/3_Approaches_To_Become_Your_Life_Coach_For_Mothers",
    "ITfC_Course_Re-wiring_womens_rights/index.php/6_Stunning_Examples_Of_Beautiful_Cleaning_houses",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Agenda",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Basic_Guidance_On_Real-World_Systems_Of_Nardi",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Best_Five_Stethoscope_for_Medicial_Professionals",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Best_Ways_To_Make_Positive_Breakthroughs_With_Your_Sales_Performance_Each_Day",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Books_And_E-Books_-_The_Handiest_Life_Coaching_Resources",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Chatten_is_altijd_gratis",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Cigarette_Electronique_Nantes_E",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Coach_Yourself:_Three_Tips_From_A_Player_Coach",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Coconut_Oil_s_Awesome_Benefits",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Coconut_Oil_s_Incredible_Benefits",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Desde_La_Oficina_Del_Consumidor_Nos_Lanzan_Unas_Recomendaciones_a_la_hora_de_Contratar_Un",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Få_Spinning_för_underhållande_och_resultat",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Get_The_Mortgage_As_Your_Convenience_At_Reduced_Curiosity",
    "ITfC_Course_Re-wiring_womens_rights/index.php/How_Discover_How_To_Handicap_Horse_Races",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Keep_company_with_Take_note_of_be_expeditious_for_Ban_Exploration_Business_down_Your_Build_Troop",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Laid_Off_-_Does_Affiliate_Advertising_Function",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Life_Coaching_-_Helping_You_To_Move_On",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Online_Life_Coaching_-_The_Loa_Equation",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Preventing_Debt_Traps_For_Young_Players_-_Australian_Housing",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Self_Defense_Goods-The_Three_Most_Efficient_In_The_Globe",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Things_about_Calculation_Before_Clever_straighten_up_Website",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Tips_to_Be_Able_To_The_Perfect_Business_Card",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Truth_about_abs_articles_of_association",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Une_analyse_perspicace_sur_identifier_des_Ã_lÃ_ments_indispensables_de_lit_mezzanine",
    "ITfC_Course_Re-wiring_womens_rights/index.php/User:AustinBrassell",
    "ITfC_Course_Re-wiring_womens_rights/index.php/User:RudyC99kypfla",
    "ITfC_Course_Re-wiring_womens_rights/index.php/Your_Sound_Judgement_Can_An_Individual_To_Lose_Weight",
    "ITfC_Course_Re-wiring_womens_rights/index.php/﻿Mujeres_Teniendo_Xexo_Con_Perros",
    # 1 spam page in the 2013-14 annual report wiki
    "ITfC_Annual_Report_2013-14/index.php/Good_Vices_That_Benefit_Our_Health",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()

    found: set[str] = set()
    by_shard: dict[str, int] = {}
    for shard in sorted(glob.glob(SHARDS)):
        with open(shard, 'r', encoding='utf-8') as f:
            pages = json.load(f)
        kept = [p for p in pages if (p.get('slug') or '') not in SPAM_SLUGS]
        dropped = len(pages) - len(kept)
        if dropped:
            for p in pages:
                if (p.get('slug') or '') in SPAM_SLUGS:
                    found.add(p['slug'])
            by_shard[shard] = dropped
            if args.apply:
                with open(shard, 'w', encoding='utf-8') as f:
                    json.dump(kept, f, ensure_ascii=False)

    missing = SPAM_SLUGS - found
    print(f'spam dropped: {len(found)} / {len(SPAM_SLUGS)} expected')
    for s, n in by_shard.items():
        print(f'  {s}: -{n}')
    if missing:
        print(f'\nNOT FOUND ({len(missing)}):')
        for s in sorted(missing):
            print(f'  {s}')
    if not args.apply:
        print('\n(dry run; pass --apply to write)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
