"""Joint exams occur on working days except independent final diary."""
from datetime import date, timedelta
import diary_batch
from diary_calendar import is_non_working_day

def main():
    cases=[(date(2026,12,28),date(2027,1,15)),(date(2027,4,28),date(2027,5,20)),(date(2027,10,1),date(2028,2,7)),(date(2026,6,10),date(2026,7,1))]
    for admission,discharge in cases:
        offsets=diary_batch._clinical_diary_offsets((discharge-admission).days)
        days=[admission+timedelta(days=o) for o in offsets]
        entries,_,_=diary_batch._build_text_diary_entries(["Пациент спокоен","Пациент сообщил об улучшении сна"],days,discharge_date_value=discharge,force_final_diary=True,repeat_statuses=True,patient_gender="male")
        joints=[e for e in entries if e.is_joint_head_exam]
        assert joints,(admission,discharge)
        assert all(e.is_final or not is_non_working_day(e.date) for e in joints),(admission,joints)
        pos=[e.sequence_number for e in joints]
        assert all(b-a>=3 for a,b in zip(pos,pos[1:])),pos
        assert len(joints)>=max(1,len(entries)//3-2)
    print("DIARY JOINT EXAM WORKING-DAY REGRESSION OK")

if __name__=="__main__": main()
