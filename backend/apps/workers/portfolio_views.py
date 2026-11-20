"""API das fotos de trabalhos anteriores do prestador (US09)."""

from django.http import FileResponse, Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.authentication import SessionAuthentication
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import DomainError
from apps.core.images import content_type_of
from apps.workers import portfolio
from apps.workers.models import PortfolioPhoto
from apps.workers.views import RESTRICTED, worker_or_403


class PortfolioAreaView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]


@method_decorator(csrf_protect, name="dispatch")
class WorkerPortfolioView(PortfolioAreaView):
    """`GET`/`POST /api/workers/me/portfolio/` (multipart: `photo` e `caption` opcional)."""

    parser_classes = [MultiPartParser]

    def get(self, request):
        worker = worker_or_403(request)
        if worker is None:
            return Response({"detail": RESTRICTED}, status=403)
        return Response({"results": portfolio.serialize_photos(worker)})

    def post(self, request):
        worker = worker_or_403(request)
        if worker is None:
            return Response({"detail": RESTRICTED}, status=403)
        try:
            portfolio.add_photo(
                worker, request.FILES.get("photo"), request.data.get("caption", "")
            )
        except DomainError as error:
            return Response({"detail": str(error)}, status=400)
        return Response({"results": portfolio.serialize_photos(worker)}, status=201)


@method_decorator(csrf_protect, name="dispatch")
class WorkerPortfolioItemView(PortfolioAreaView):
    """`DELETE /api/workers/me/portfolio/<id>/`: só o próprio prestador remove a sua foto."""

    def delete(self, request, pk):
        worker = worker_or_403(request)
        if worker is None:
            return Response({"detail": RESTRICTED}, status=403)
        photo = PortfolioPhoto.objects.filter(pk=pk, worker=worker).first()
        if photo is None:
            return Response({"detail": "Foto não encontrada."}, status=404)
        portfolio.remove_photo(photo)
        return Response(status=204)


class PortfolioFileView(PortfolioAreaView):
    """`GET /api/workers/portfolio/<id>/file/`: dono, admin ou empresa com candidatura dele."""

    def get(self, request, pk):
        photo = PortfolioPhoto.objects.select_related("worker").filter(pk=pk).first()
        if photo is None or not portfolio.can_view(request.user, photo.worker):
            raise Http404
        try:
            handle = photo.file.open("rb")
        except FileNotFoundError:
            raise Http404 from None
        response = FileResponse(handle, content_type=content_type_of(photo.file.name))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
