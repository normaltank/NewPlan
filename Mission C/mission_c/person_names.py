"""Name shapes, not identity proof. Preserve Unicode and Latin word boundaries."""
import re
import unicodedata

HAN_CHARS='\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f\U00030000-\U000323af'
CHINESE=re.compile('['+HAN_CHARS+'·・]{2,8}')
NON_NAMES={'faculty members','academic staff','teaching staff','contact us','read more','no data','news list','research team','home page','about us','privacy policy','all rights reserved'}

def clean_name(value):
    value=re.sub(r'[\u200b\ufeff]','',unicodedata.normalize('NFKC',value or '')).strip()
    # CJK names use spacing for typography. Latin names need their word spaces.
    if re.fullmatch('['+HAN_CHARS+r'·・\s]+',value):return re.sub(r'\s+','',value)
    return re.sub(r'\s+',' ',value)

def is_person_name(value):
    value=clean_name(value)
    if CHINESE.fullmatch(value):return True
    if len(value)>80 or value.casefold() in NON_NAMES:return False
    words=value.split()
    if not 2<=len(words)<=6:return False
    for word in words:
        letters=[c for c in word if c.isalpha()]
        if not letters or any('LATIN' not in unicodedata.name(c,'') for c in letters):return False
        if any(not(c.isalpha() or c in "-'’.") for c in word):return False
        if len(letters)==1 and not word.endswith('.'):return False
    return True
