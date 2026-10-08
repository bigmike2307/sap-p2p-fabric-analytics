@AbapCatalog.viewEnhancementCategory: [#NONE]
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'P2P extraction: cleared supplier items'
@Metadata.ignorePropagatedAnnotations: true
@ObjectModel.usageType: { serviceQuality: #D, sizeCategory: #XL, dataClass: #TRANSACTIONAL }
@Analytics.dataCategory: #FACT
@Analytics.dataExtraction.enabled: true
@Analytics.dataExtraction.delta.changeDataCapture.automatic: true
// In S/4HANA, BSAK is a compatibility view, so CDC cannot track it. This view reads the
// cleared supplier line items from BSEG directly and keeps the BSAK field names.
define view entity ZX_P2P_BSAK
  as select from bseg
{
  key bukrs,
  key belnr,
  key gjahr,
  key buzei,
      lifnr,
      augdt,
      augbl,
      h_budat as budat,
      h_bldat as bldat,
      h_waers as waers,
      h_blart as blart,
      shkzg,
      // DMBTR is in company-code currency (T001-WAERS), which is not on BSEG
      cast( dmbtr as abap.dec( 13, 2 ) ) as dmbtr,
      @Semantics.amount.currencyCode: 'waers'
      wrbtr,
      zfbdt,
      zterm,
      zbd1t
}
where
      koart = 'K' // supplier (vendor) line items
  and augbl <> '' // cleared, i.e. paid
