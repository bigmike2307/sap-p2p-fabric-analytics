@AbapCatalog.viewEnhancementCategory: [#NONE]
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'P2P extraction: purchase order history'
@Metadata.ignorePropagatedAnnotations: true
@ObjectModel.usageType: { serviceQuality: #D, sizeCategory: #XL, dataClass: #TRANSACTIONAL }
@Analytics.dataCategory: #FACT
@Analytics.dataExtraction.enabled: true
@Analytics.dataExtraction.delta.changeDataCapture.automatic: true
define view entity ZX_P2P_EKBE
  as select from ekbe
{
  key ebeln,
  key ebelp,
  key zekkn,
  key vgabe,
  key gjahr,
  key belnr,
  key buzei,
      bewtp,
      bwart,
      budat,
      // quantity references the order unit on EKPO-MEINS
      cast( menge as abap.dec( 13, 3 ) ) as menge,
      @Semantics.amount.currencyCode: 'hswae'
      dmbtr,
      @Semantics.amount.currencyCode: 'waers'
      wrbtr,
      waers,
      hswae,
      @Semantics.amount.currencyCode: 'hswae'
      arewr,
      shkzg,
      lfgja,
      lfbnr,
      lfpos,
      cpudt,
      ernam
}
where
     vgabe = '1' // goods receipt
  or vgabe = '2' // invoice receipt
