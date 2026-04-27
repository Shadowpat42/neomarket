from rest_framework.views import APIView
from rest_framework.response import Response


class ProductListCreateView(APIView):
    def post(self, request):
        return Response({
            "message": "Product creation endpoint skeleton"
        })


class ProductDetailView(APIView):
    def get(self, request, product_id):
        return Response({
            "id": product_id,
            "message": "Product detail endpoint skeleton"
        })

    def put(self, request, product_id):
        return Response({
            "id": product_id,
            "message": "Product update endpoint skeleton"
        })