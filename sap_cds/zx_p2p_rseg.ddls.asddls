@AbapCatalog.viewEnhancementCategory: [#NONE]
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'P2P extraction: supplier invoice item'
@Metadata.ignorePropagatedAnnotations: true
@ObjectModel.usageType: { serviceQuality: #D, sizeCategory: #XL, dataClass: #TRANSACTIONAL }
@Analytics.dataCategory: #FACT
@Analytics.dataExtraction.enabled: true
@Analytics.dataExtraction.delta.changeDataCapture.automatic: true
define view entity ZX_P2P_RSEG
  as select from rseg
{
  key belnr,
  key gjahr,
  key buzei,
      ebeln,
      ebelp,
      matnr,
      werks,
      // WRBTR references the invoice currency on RBKP-WAERS
      cast( wrbtr as abap.dec( 13, 2 ) ) as wrbtr,
      shkzg,
      mwskz,
      @Semantics.quantity.unitOfMeasure: 'bstme'
      menge,
      bstme,
      lfbnr,
      lfgja,
      lfpos
}
