"""Serve public reviews on the existing paid OS with its Dropbox connection."""
from fastapi import FastAPI
from reviews_http import router

PUBLIC_ORIGIN='https://sports-cave-image-factory.onrender.com'

class PublicReviews:
    def __init__(self,application):
        self.application=application
        self.reviews=FastAPI(openapi_url=None,docs_url=None,redoc_url=None)
        self.reviews.include_router(router)
    async def __call__(self,scope,receive,send):
        target=self.reviews if scope.get('type')=='http' and scope.get('path','').startswith('/reviews/') else self.application
        await target(scope,receive,send)

def public_base(env):
    return (env.get('REVIEWS_PUBLIC_BASE_URL') or (PUBLIC_ORIGIN if env.get('RENDER') else env.get('CRM_PUBLIC_BASE_URL',''))).rstrip('/')
