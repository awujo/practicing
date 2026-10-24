from types import SimpleNamespace
import json
from bishop.collect_teacher_schedules import collect_symbol_schedules
from ctrader.framing import model,oa


def test_schedule_export_is_allowlisted_and_not_historical_certification(tmp_path):
    symbol=model.ProtoOASymbol(symbolId=5,digits=2,pipPosition=1,minVolume=100,maxVolume=10000,stepVolume=100)
    symbol.scheduleTimeZone='Europe/London';symbol.schedule.add(startSecond=300,endSecond=500)
    symbol.holiday.add(holidayId=8,name='holiday',holidayDate=20260101,isRecurring=False,startSecond=0,endSecond=100)
    class Client:
        account_id=999
        def symbol(self,name):return {'symbol_id':5,'name':name}
        def request(self,request):
            assert isinstance(request,oa.ProtoOASymbolByIdReq)
            return SimpleNamespace(symbol=[symbol])
    result=collect_symbol_schedules(Client(),{'X':{'broker_symbol':'X'}},tmp_path,retrieved_at='2026-10-24T00:00:00Z')
    assert result['certification']=='NOT_HISTORICAL_CALENDAR_CERTIFICATION'
    record=result['symbols'][0]['record']
    assert record['schedule']==[{'startSecond':300,'endSecond':500}]
    assert record['holiday'][0]['holidayId']==8
    raw=(tmp_path/'symbol_schedules.json').read_text()
    assert '999' not in raw and 'minVolume' not in raw and 'maxVolume' not in raw
    assert set(record)=={'symbolId','name','digits','pipPosition','scheduleTimeZone','schedule','holiday'}
