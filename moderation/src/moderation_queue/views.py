from rest_framework.views import APIView
from rest_framework.response import Response


class GetNextProductView(APIView):
    def post(self, request):
        return Response({
            "message": "Get next product for moderation skeleton"
        })