@AbapCatalog.viewEnhancementCategory: [#NONE]
@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'P2P extraction: supplier invoice header'
@Metadata.ignorePropagatedAnnotations: true
@ObjectModel.usageType: { serviceQuality: #D, sizeCategory: #L, dataClass: #TRANSACTIONAL }
@Analytics.dataCategory: #FACT
@Analytics.dataExtraction.enabled: true
@Analytics.dataExtraction.delta.changeDataCapture.automatic: true
define view entity ZX_P2P_RBKP
  as select from rbkp
{
  key belnr,
  key gjahr,
      blart,
      bldat,
      budat,
      usnam,
      cpudt,
      xblnr,
      bukrs,
      lifnr,
      waers,
      @Semantics.amount.currencyCode: 'waers'
      rmwwr,
      @Semantics.amount.currencyCode: 'waers'
      wmwst1,
      mwskz1,
      zterm,
      zbd1t,
      zfbdt,
      zlspr,
      rbstat
}
