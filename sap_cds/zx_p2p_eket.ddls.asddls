@AbapCatalog.viewEnhancementCategory: [#NONE]
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'P2P extraction: purchase order schedule line'
@Metadata.ignorePropagatedAnnotations: true
@ObjectModel.usageType: { serviceQuality: #D, sizeCategory: #XL, dataClass: #TRANSACTIONAL }
@Analytics.dataCategory: #FACT
@Analytics.dataExtraction.enabled: true
@Analytics.dataExtraction.delta.changeDataCapture.automatic: true
define view entity ZX_P2P_EKET
  as select from eket
{
  key ebeln,
  key ebelp,
  key etenr,
      eindt,
      slfdt,
      // quantities reference the order unit on EKPO-MEINS
      cast( menge as abap.dec( 13, 3 ) ) as menge,
      cast( wemng as abap.dec( 13, 3 ) ) as wemng
}
