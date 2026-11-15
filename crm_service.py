"""CRM request boundary: existing account permissions plus disabled-by-default gates."""
import uuid
from crm_navigation import require
from crm_resend import Config
from crm_logic import email,recipient_hash,date,now,validate_steps,validate_rules

def audit(action,object_id,user):
    from activity_log import record_activity_log
    record_activity_log(action_type='crm_'+action,page='CRM & Marketing',message='CRM '+action.replace('_',' '),entity_type='crm',entity_id=str(object_id),metadata={},actor=str(user.get("id") or user.get("username") or ""))

class Actions:
    def __init__(self,store,user,config=None):self.store,self.user,self.config=store,user,config or Config()
    def seed(self):
        import os_accounts
        require(self.user,'crm_automations_manage')
        if not os_accounts.is_admin(self.user):raise PermissionError('An administrator initializes the draft library.')
        self.store.seed();audit('draft_library_initialized','library',self.user)
    def segment(self,name,rules,object_id=None):
        require(self.user,'crm_segments_view');validate_rules(rules)
        result=self.store.save_segment(name,rules,self.user.get('id',''),object_id);audit('segment_saved',result['id'],self.user);return result
    def template(self,row,name,content):
        require(self.user,'crm_templates_manage')
        result=self.store.save_template(row['id'],name,content);audit('template_saved',row['id'],self.user);return result
    def automation(self,row,steps,config,status):
        require(self.user,'crm_automations_manage')
        if status=='ACTIVE':
            from crm_resend import MarketingDisabled
            raise MarketingDisabled('Flow activation is disabled during the campaigns-first foundation stage.')
        validate_steps(steps)
        if not 1<=int(config.get('days',180))<=3650:raise ValueError('Use 1–3650 days.')
        self.store.save_automation(row['id'],steps,config,status);audit('automation_saved',row['id'],self.user)
    def campaign(self,name,template,segment_id=None,definition_id=None):
        require(self.user,'crm_campaigns_manage')
        if not name.strip():raise ValueError('Campaign name is required.')
        row=self.store.save_campaign(name,template,segment_id,definition_id);audit('campaign_created',row['id'],self.user);return row
    def schedule(self,row,at):
        require(self.user,'crm_campaigns_manage')
        from crm_resend import MarketingDisabled
        raise MarketingDisabled('Production campaign scheduling is disabled in this stage.')
    def resume(self,row):
        require(self.user,'crm_campaigns_manage')
        from crm_resend import MarketingDisabled
        raise MarketingDisabled('Production campaign resuming is disabled in this stage.')
    def test(self,template,address,request_id):
        require(self.user,'crm_campaigns_manage');self.config.require_send(test=True)
        if not email(address):raise ValueError('Enter one explicit test email address.')
        key='test:'+str(uuid.UUID(request_id))
        row=self.store.enqueue(key,None,recipient_hash(address),template,test_recipient=email(address))
        audit('test_queued',key,self.user);return row
    def pause(self,row):
        require(self.user,'crm_campaigns_manage');self.store.pause_campaign(row['id']);audit('campaign_paused',row['id'],self.user)
