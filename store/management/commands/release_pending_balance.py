from django.core.management.base import BaseCommand
from django.utils import timezone
from store.models import WalletTransaction, WalletTransaction
from datetime import timedelta

class Command(BaseCommand):
    help = 'تحرير الأرباح المعلقة بعد 24 ساعة'

    def handle(self, *args, **kwargs):
        # الوقت قبل 24 ساعة
        time_threshold = timezone.now() - timedelta(hours=24)
        
        # البحث عن المعاملات المعلقة القديمة
        pending_txs = WalletTransaction.objects.filter(
            transaction_type='PENDING',
            created_at__lte=time_threshold,
            is_released=False # حقل سنضيفه للمعاملة
        )

        for tx in pending_txs:
            wallet = tx.wallet
            
            # نقل من المعلق للمتاح
            wallet.pending_balance -= tx.amount
            wallet.balance += tx.amount
            wallet.save()
            
            # تحديث المعاملة
            tx.transaction_type = 'SALE' # تحولت لبيع حقيقي
            tx.is_released = True
            tx.save()
            
            self.stdout.write(self.style.SUCCESS(f'Released {tx.amount} for {wallet.merchant}'))