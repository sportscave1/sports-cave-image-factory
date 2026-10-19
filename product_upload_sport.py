"""Product Upload-only folder selection and metadata rebinding; no pixel work."""
import streamlit as st
from product_upload_export import sport_categories,resolve_category


def state_key(key):
    return 'product-upload-category-'+str(key)


def clear_selection(key):
    prefix=state_key(key)
    for name in list(st.session_state):
        if name==prefix or name.startswith(prefix+'-'):st.session_state.pop(name,None)


def selected(key):
    return st.session_state.get(state_key(key)+'-resolved')


def render_selector(app,key,user,*,disabled=False):
    state=state_key(key);api=app.dropbox_integration
    error=st.session_state.pop(state+'-error','')
    choice=None
    try:
        if not app.os_accounts.can_access_page(user,'Files'):
            raise ValueError('Files access is required to select a sport destination.')
        token=app._files_access_token();root=app._files_team_root(token)
        cache=st.session_state.get(state+'-folders')
        if not cache or cache['root']!=root or cache['actor']!=user['id']:
            cache=dict(root=root,actor=user['id'],items=sport_categories(api,token,root))
            st.session_state[state+'-folders']=cache
        options={x['id']:x for x in cache['items'] if x.get('id')}
        # Resolve retained ID before rendering: renames update labels and paths;
        # removals stay unselected, never fall back to the first available sport.
        retained=st.session_state.get(state+'-id')
        if retained:
            try:
                choice=resolve_category(api,token,root,retained)
                options[retained]=choice
            except Exception:
                error='The selected sport folder is unavailable or moved. Refresh the choices and select an available folder.'
                st.session_state.pop(state+'-folders',None)
                refreshed=sport_categories(api,token,root)
                options={x['id']:x for x in refreshed if x.get('id') and x['id']!=retained}
                st.session_state.pop(state,None)
                st.session_state.pop(state+'-id',None)
        def changed():
            st.session_state[state+'-id']=st.session_state.get(state)
        if state not in st.session_state and retained in options:st.session_state[state]=retained
        ids=sorted(options,key=lambda i:options[i]['name'].casefold())
        category_id=st.selectbox('Sport category',ids,index=None,format_func=lambda i:options[i]['name'],
            placeholder='Select a sport category',key=state,on_change=changed,disabled=disabled)
        if category_id and not error:choice=resolve_category(api,token,root,category_id)
        else:choice=None
        if not category_id and not error:st.caption('Select the sport once; Save all uses this Dropbox folder.')
    except Exception as exc:
        error=str(exc) if isinstance(exc,ValueError) else 'Dropbox sport folders could not be read. Check Files access and refresh the choices.'
        st.session_state.pop(state+'-folders',None)
        choice=None
    st.session_state[state+'-resolved']=choice
    if error:st.error(error)
    if st.button('Refresh sport folders',key=state+'-refresh',disabled=disabled):
        st.session_state.pop(state+'-folders',None);st.rerun()
    return choice


def rebind_result(app,result,name,choice):
    """Rebuild the existing filename manifest while retaining original paths."""
    if not choice or not name.strip():return result
    if (result.get('product_name'),result.get('sport_category'),result.get('_product_upload_category_id'))==(name.strip(),choice['sport'],choice['id']):return result
    factory=app.get_image_factory()
    result=dict(result,product_name=name.strip(),product_slug=factory.slugify(name),
                sport_category=choice['sport'],sport_slug=factory.slugify(choice['sport']),
                _product_upload_category_id=choice['id'])
    result['final_prompt_items']=app.build_mockup_final_prompt_items(name.strip(),choice['sport'])
    result.pop('product_upload_save_receipt',None)
    return app.normalize_generation_result(result)
