#include <stdio.h>
void main(){
	int num,sum,i;
	sum = 0;
	printf("정수를 1개 입력하시오: ");
	scanf("%d",&num);
	for(i=1;i<=num;i++)
	 {if(i%2!=0)
	  sum = sum+i;}
	 printf("홀수의 총합은%d입니다.",sum);
}

